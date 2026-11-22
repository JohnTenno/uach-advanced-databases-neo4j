// Optimistic actions: the page changes at once, the request goes in the background,
// and on failure the view goes back to how it was and a toast explains why.
// Without JavaScript every form still works as a normal POST.
(() => {
  const toasts = document.createElement("div");
  toasts.className = "toasts";
  toasts.setAttribute("aria-live", "assertive");
  document.body.appendChild(toasts);

  function toast(message) {
    const item = document.createElement("div");
    item.className = "notice notice-error toast";
    item.setAttribute("role", "alert");
    item.textContent = message;
    toasts.appendChild(item);
    setTimeout(() => item.remove(), 6000);
  }

  async function send(form, body = new FormData(form)) {
    let response;
    try {
      response = await fetch(form.action, {
        method: "POST", body, credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
    } catch {
      throw new Error("No hay conexión con el servidor. No se guardó el cambio.");
    }
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) {
      form.dispatchEvent(new CustomEvent("session-expired"));
      location.href = "/auth/login?expired=1&next=" + encodeURIComponent(location.pathname);
      throw new Error("Tu sesión expiró.");
    }
    if (!response.ok) throw new Error(data.message || "No se pudo completar la acción.");
    return data;
  }

  // The number and its screen-reader word ("comentario"/"comentarios") change together.
  const countWord = (el, value) => {
    el.textContent = value;
    const word = el.nextElementSibling;
    if (word?.classList.contains("sr-only")) word.textContent = Number(value) === 1 ? "comentario" : "comentarios";
  };
  const setCounts = (value) => document.querySelectorAll("[data-comment-count]").forEach((el) => countWord(el, value));
  const commentCount = () => Number(document.querySelector("[data-comment-count]")?.textContent || 0);

  const handlers = {
    async like(form) {
      const button = form.querySelector("button");
      const counter = button.querySelector("[data-like-count]");
      const before = { liked: button.getAttribute("aria-pressed") === "true", count: Number(counter.textContent) };
      const paint = ({ liked, count }) => {
        button.setAttribute("aria-pressed", String(liked));
        button.classList.toggle("action--on", liked);
        button.querySelector("svg").setAttribute("fill", liked ? "currentColor" : "none");
        button.setAttribute("aria-label", `${liked ? "Quitar me gusta" : "Me gusta"} (${count})`);
        counter.textContent = count;
      };
      const want = form.querySelector("[name=want]");
      paint({ liked: !before.liked, count: before.count + (before.liked ? -1 : 1) });
      try {
        const body = new FormData(form);
        body.set("want", before.liked ? "0" : "1");
        const data = await send(form, body);
        want.value = data.liked ? "0" : "1";
        paint({ liked: data.liked, count: data.like_count });
      } catch (error) {
        paint(before);
        throw error;
      }
    },

    async "comment-create"(form) {
      const textarea = form.querySelector("textarea");
      const list = document.querySelector(".comments");
      const empty = list.querySelector(".comments-empty");
      const name = form.querySelector("[name=name]")?.value || "";
      // A greyed-out preview of the comment until the server confirms it.
      const pending = document.createElement("li");
      pending.className = "comment comment--pending";
      pending.innerHTML = '<span class="avatar avatar--sm" aria-hidden="true"></span><div class="comment-body">' +
        '<div class="comment-head"><strong></strong><span class="muted">Publicando…</span></div><p></p></div>';
      pending.querySelector(".avatar").textContent = (name[0] || "?").toUpperCase();
      pending.querySelector("strong").textContent = name;
      pending.querySelector("p").textContent = textarea.value;
      const typed = textarea.value;
      const body = new FormData(form); // read before the textarea is cleared below
      // If the session expired, keep the text so it comes back after logging in.
      const keep = () => { try { sessionStorage.setItem(draftKey, typed); } catch {} };
      form.addEventListener("session-expired", keep, { once: true });
      const before = commentCount();
      empty?.remove();
      list.appendChild(pending);
      setCounts(before + 1);
      textarea.value = "";
      try {
        const data = await send(form, body);
        pending.outerHTML = data.html;
        setCounts(data.count);
      } catch (error) {
        pending.remove();
        if (empty) list.appendChild(empty);
        setCounts(before);
        if (!textarea.value.trim()) textarea.value = typed; // never overwrite what was typed meanwhile
        throw error;
      } finally {
        form.removeEventListener("session-expired", keep);
      }
    },

    async "comment-delete"(form) {
      const item = form.closest("li");
      const list = item.parentElement;
      const before = commentCount();
      item.hidden = true;
      setCounts(before - 1);
      try {
        const data = await send(form);
        item.remove();
        setCounts(data.count);
        if (!list.querySelector("li.comment")) {
          list.insertAdjacentHTML("beforeend", '<li class="muted comments-empty">Nadie ha comentado todavía.</li>');
        }
      } catch (error) {
        item.hidden = false;
        setCounts(before);
        throw error;
      }
    },
  };

  // A comment saved when the session expired comes back into its box.
  const draftKey = "comment-draft:" + location.pathname;
  try {
    const saved = sessionStorage.getItem(draftKey);
    const box = document.querySelector("form[data-async=comment-create] textarea");
    if (saved && box && !box.value) { box.value = saved; sessionStorage.removeItem(draftKey); }
  } catch {}

  const busy = new WeakSet();
  document.addEventListener("submit", async (event) => {
    const form = event.target;
    const handler = handlers[form.dataset.async];
    // The confirm dialog prevents the first submit and re-submits once confirmed.
    if (!handler || event.defaultPrevented || (form.dataset.confirmTitle && !form.dataset.confirmed)) return;
    event.preventDefault();
    if (busy.has(form)) return;
    busy.add(form);
    try {
      await handler(form);
    } catch (error) {
      toast(error.message);
    } finally {
      busy.delete(form);
      delete form.dataset.confirmed;
      form.querySelector("input[name=confirm]")?.remove();
    }
  });
  // Loading state for every normal POST (save, publish, delete, edit profile...): the clicked
  // button shows a spinner and the form can't be sent twice. Likes and comments are optimistic.
  const loadingLabel = (text) =>
    /eliminar/i.test(text) ? "Eliminando…" : /publicar/i.test(text) ? "Publicando…"
    : /entrar|iniciar/i.test(text) ? "Entrando…" : /cerrar sesión/i.test(text) ? "Cerrando sesión…"
    : /crear/i.test(text) ? "Creando…" : "Guardando…";
  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (event.defaultPrevented || form.dataset.async || form.method.toLowerCase() !== "post") return;
    if (form.dataset.sending) { event.preventDefault(); return; }
    form.dataset.sending = "1";
    const button = event.submitter || form.querySelector("button[type=submit], button:not([type])");
    // A disabled submitter is left out of the form data, so its name/value (publish/draft) goes as a hidden field.
    if (button?.name) form.append(Object.assign(document.createElement("input"), { type: "hidden", name: button.name, value: button.value, className: "js-submitter" }));
    form.querySelectorAll("button").forEach((b) => { b.disabled = true; });
    form.setAttribute("aria-busy", "true");
    if (button) {
      button.dataset.label = button.innerHTML;
      button.classList.add("is-loading");
      button.innerHTML = `<span class="spinner" aria-hidden="true"></span>${loadingLabel(button.textContent)}`;
    }
  });
  // Coming back with the browser's Back button shows the page as it was left: undo the loading state.
  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) return;
    document.querySelectorAll("form[data-sending]").forEach((form) => {
      delete form.dataset.sending;
      form.removeAttribute("aria-busy");
      form.querySelectorAll(".js-submitter").forEach((el) => el.remove());
      form.querySelectorAll("button").forEach((b) => {
        b.disabled = false;
        if (b.dataset.label) { b.innerHTML = b.dataset.label; b.classList.remove("is-loading"); delete b.dataset.label; }
      });
    });
  });

  // Sticky side column like X/Twitter: if it is taller than the screen, a negative top lets it
  // scroll with the page until its end shows, then it stays put. No nested scrollbar.
  const side = document.querySelector(".home-side");
  if (side && "ResizeObserver" in window) {
    const fit = () => {
      const room = window.innerHeight - 40;
      side.style.top = side.offsetHeight > room ? `${room - side.offsetHeight + 20}px` : "20px";
    };
    new ResizeObserver(fit).observe(side);
    window.addEventListener("resize", fit);
  }

  // Reveal animations (motion proposal by Codex, after the GAMEPLAY section of the Endfield site):
  // a yellow block sweeps the image, the image opens 110 ms behind it, then content "locks in"
  // with hard on/off cuts. Each element plays once, when it first enters the screen.
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!still && "IntersectionObserver" in window && Element.prototype.animate) {
    window.__revealReady = true;
    const running = new Set();
    const play = (el, frames, duration, delay = 0, easing = "linear") => {
      const a = el.animate(frames, { duration, delay, fill: "both", easing });
      running.add(a);
      // Safety net: if the browser pauses the timeline (hidden tab), never leave content covered.
      setTimeout(() => { try { a.finish(); } catch {} running.delete(a); }, delay + duration + 1500);
      return a;
    };
    document.addEventListener("visibilitychange", () => { if (document.hidden) running.forEach((a) => { try { a.finish(); } catch {} }); });
    const flicker = (el, start, duration = 240) => play(el,
      [[0, 0], [1, .18], [0, .31], [1, .46], [0, .59], [1, .76], [1, 1]]
        .map(([opacity, offset]) => ({ opacity, offset, easing: "steps(1, end)" })), duration, start);
    const media = (el) => {
      const visual = el.querySelector("img, span");
      const wipe = document.createElement("i");
      wipe.className = "rv-wipe";
      el.append(wipe);
      play(wipe, [
        { transform: "translateX(-101%)", offset: 0, easing: "cubic-bezier(.22,.7,.24,1)" },
        { transform: "translateX(0%)", offset: .38, easing: "cubic-bezier(.65,0,.25,1)" },
        { transform: "translateX(101%)", offset: 1 },
      ], 580).finished.then(() => wipe.remove(), () => {});
      if (visual) {
        play(visual, [{ clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)" }], 470, 110, "cubic-bezier(.16,1,.3,1)");
        flicker(visual, 440);
      }
    };
    // Panels (side cards, admin lists, forms, login): no wipe here, only the text flicker,
    // in reading order: titles first, then the contents one after another.
    const TITLES = "h1, h2, h3, .eyebrow, .title, .section-title, .brand";
    const parts = (el) => [...el.children].flatMap((child) => {
      if (child.matches("form")) return parts(child);
      if (child.matches(".table-wrap")) return [...child.querySelectorAll("tr")];
      return [child];
    });
    const panel = (el) => {
      const index = [...el.parentElement.children].filter((c) => c.matches(PANELS)).indexOf(el);
      const start = Math.max(0, index) * 140;
      const items = parts(el);
      const ordered = [...items.filter((i) => i.matches(TITLES)), ...items.filter((i) => !i.matches(TITLES))];
      ordered.forEach((item, i) => flicker(item, start + Math.min(i, 10) * 70, 240));
      // The CSS pre-hide covers direct children; the animations above own the visibility now.
      [...el.children].forEach((child) => { child.style.opacity = "1"; });
    };
    const PANELS = ".home-side > *, .admin-panel, .form-panel, .frame-profile, .auth-card";
    const seen = new IntersectionObserver((entries) => entries.forEach(({ isIntersecting, target }) => {
      if (!isIntersecting) return;
      seen.unobserve(target);
      if (target.dataset.reveal === "media") media(target);
      else if (target.matches(PANELS)) panel(target);
      else flicker(target, Number(target.dataset.delay || 0), 260);
    }), { threshold: 0 }); // 0: a tall panel (users list on a phone) may never reach a ratio.
    document.querySelectorAll(`[data-reveal], ${PANELS}`).forEach((el) => seen.observe(el));
  } else {
    document.documentElement.classList.remove("js-reveal");
  }

  // Live updates (Server-Sent Events): other people's likes, comments and posts show up
  // without reloading. Events only carry ids and counts; content comes through normal routes.
  const me = document.body.dataset.me;
  if (me && "EventSource" in window) {
    const stream = new EventSource("/events");
    const on = (kind, fn) => stream.addEventListener(kind, (event) => {
      const data = JSON.parse(event.data);
      if (String(data.by) !== me) fn(data);
    });

    on("like", ({ article_id, count }) => {
      document.querySelectorAll(`#articulo-${article_id} [data-like-count]`).forEach((counter) => {
        counter.textContent = count;
        const button = counter.closest("button");
        const liked = button.getAttribute("aria-pressed") === "true";
        button.setAttribute("aria-label", `${liked ? "Quitar me gusta" : "Me gusta"} (${count})`);
      });
    });

    on("comment", async ({ article_id, count }) => {
      document.querySelectorAll(`#articulo-${article_id} [data-card-comments]`).forEach((el) => countWord(el, count));
      const list = document.querySelector(".comments");
      if (!list || !document.getElementById(`articulo-${article_id}`)) return;
      try {
        const page = await fetch(location.pathname, { credentials: "same-origin" });
        if (!page.ok) return;
        const fresh = new DOMParser().parseFromString(await page.text(), "text/html").querySelector(".comments");
        if (fresh && !list.querySelector(".comment--pending, li[hidden]")) list.innerHTML = fresh.innerHTML;
        setCounts(count);
      } catch {}
    });

    let banner;
    on("post", async () => {
      const feed = document.querySelector("section.feed");
      if (!feed || banner) return;
      // Near the top of page 1 the new post just slides in; further down a banner avoids moving what is being read.
      const params = new URLSearchParams(location.search);
      if (window.scrollY < 300 && (params.get("page") || "1") === "1") {
        try {
          const page = await fetch(location.href, { credentials: "same-origin" });
          const fresh = page.ok && new DOMParser().parseFromString(await page.text(), "text/html").querySelector("section.feed");
          if (fresh) { feed.innerHTML = fresh.innerHTML; return; }
        } catch {}
      }
      banner = document.createElement("button");
      banner.type = "button";
      banner.className = "btn btn-primary live-banner";
      banner.textContent = "Hay publicaciones nuevas · Actualizar";
      banner.addEventListener("click", () => location.reload());
      feed.prepend(banner);
    });
  }
})();
