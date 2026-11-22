// Consultas para revisar el grafo del blog en Neo4j Desktop.
// Algunas consultas usan parametros. En Neo4j Browser o cypher-shell, antes de correrlas:
//   :param articulo => 1
//   :param usuario => 3
// El borrado es logico: lo eliminado tiene deleted_at, por eso las consultas lo filtran.

// 1. Todo el grafo vivo (sin contadores ni nodos eliminados)
MATCH (n) WHERE NOT n:Counter AND n.deleted_at IS NULL
OPTIONAL MATCH (n)-[r]->(m) WHERE m.deleted_at IS NULL
RETURN n, r, m;

// 2. Articulos con su autor y numero de comentarios
MATCH (u:User)-[:WROTE]->(a:Article) WHERE a.deleted_at IS NULL
RETURN a.title AS articulo, u.name AS autor, a.status AS estado,
       COUNT { (a)<-[:ON]-(c:Comment) WHERE c.deleted_at IS NULL } AS comentarios
ORDER BY a.post_date DESC;

// 3. Comentarios de un articulo y quien los dejo ($articulo)
MATCH (c:Comment)-[:ON]->(a:Article {article_id: $articulo}) WHERE c.deleted_at IS NULL
OPTIONAL MATCH (u:User)-[:POSTED]->(c) WHERE u.deleted_at IS NULL
RETURN c.name AS nombre, u.email AS cuenta, c.body_text AS comentario;

// 4. Etiquetas y categorias de cada articulo
MATCH (a:Article) WHERE a.deleted_at IS NULL
RETURN a.title AS articulo,
       [(a)-[:TAGGED]->(t) WHERE t.deleted_at IS NULL | t.name] AS etiquetas,
       [(a)-[:IN_CATEGORY]->(c) WHERE c.deleted_at IS NULL | c.name] AS categorias;

// 5. Etiquetas mas usadas
MATCH (t:Tag) WHERE t.deleted_at IS NULL
RETURN t.name AS etiqueta, COUNT { (a:Article)-[:TAGGED]->(t) WHERE a.deleted_at IS NULL } AS usos
ORDER BY usos DESC;

// 6. Articulos parecidos: comparten etiquetas
MATCH (a:Article)-[:TAGGED]->(t:Tag)<-[:TAGGED]-(b:Article)
WHERE a.article_id < b.article_id AND a.deleted_at IS NULL AND b.deleted_at IS NULL AND t.deleted_at IS NULL
RETURN a.title, b.title, collect(t.name) AS etiquetas_en_comun;

// 7. Usuarios que comentaron articulos de otro usuario
MATCH (lector:User)-[:POSTED]->(c:Comment)-[:ON]->(a:Article)<-[:WROTE]-(autor:User)
WHERE lector <> autor AND c.deleted_at IS NULL AND a.deleted_at IS NULL
  AND lector.deleted_at IS NULL AND autor.deleted_at IS NULL
RETURN DISTINCT lector.name AS lector, autor.name AS autor;

// 8. Usuarios y su rol (el hash nunca se muestra en la app)
MATCH (u:User) WHERE u.deleted_at IS NULL
RETURN u.name AS nombre, u.email AS correo, u.role AS rol ORDER BY u.user_id;

// 9. Articulos con mas likes
MATCH (a:Article {status: 'PUBLISHED'}) WHERE a.deleted_at IS NULL
RETURN a.title AS articulo, COUNT { (u:User)-[:LIKED]->(a) WHERE u.deleted_at IS NULL } AS likes
ORDER BY likes DESC;

// 10. Recomendacion para $usuario: lo que les gusto a quienes coinciden con el en algun like
MATCH (yo:User {user_id: $usuario})-[:LIKED]->(comun:Article)<-[:LIKED]-(otro:User)-[:LIKED]->(rec:Article)
WHERE NOT (yo)-[:LIKED]->(rec) AND rec.status = 'PUBLISHED'
  AND yo.deleted_at IS NULL AND otro.deleted_at IS NULL
  AND comun.deleted_at IS NULL AND rec.deleted_at IS NULL
RETURN rec.title AS recomendado, count(DISTINCT otro) AS por_cuantos ORDER BY por_cuantos DESC;

// 11. Papelera: lo que se elimino logicamente y cuando
MATCH (n) WHERE n.deleted_at IS NOT NULL
RETURN labels(n)[0] AS tipo,
       coalesce(n.title, n.deleted_name, n.name, n.body_text) AS que,
       n.deleted_at AS eliminado
ORDER BY eliminado DESC;

// 12. Perfil de un usuario (pantalla "Mi perfil"): publicaciones, comentarios y likes recibidos
MATCH (u:User {user_id: $usuario}) WHERE u.deleted_at IS NULL
RETURN u.name AS nombre, u.role AS rol, u.avatar AS foto, u.cover AS portada,
       COUNT { (u)-[:WROTE]->(a:Article {status: 'PUBLISHED'}) WHERE a.deleted_at IS NULL } AS publicaciones,
       COUNT { (u)-[:POSTED]->(c:Comment)-[:ON]->(a:Article)
               WHERE c.deleted_at IS NULL AND a.deleted_at IS NULL } AS comentarios,
       COUNT { (f:User)-[:LIKED]->(a:Article {status: 'PUBLISHED'})<-[:WROTE]-(u)
               WHERE f.deleted_at IS NULL AND a.deleted_at IS NULL } AS likes_recibidos;

// 13. Feed del inicio paginado: pagina 2 de 10 en 10, lo mas nuevo primero
MATCH (u:User)-[:WROTE]->(a:Article {status: 'PUBLISHED'}) WHERE a.deleted_at IS NULL
RETURN a.article_id AS id, a.title AS titulo, u.name AS autor, a.post_date AS fecha
ORDER BY a.post_date DESC, a.article_id DESC
SKIP 10 LIMIT 10;

// 14. Pestaña "Fotos" del perfil: publicaciones con imagen de un autor
MATCH (u:User {user_id: $usuario})-[:WROTE]->(a:Article {status: 'PUBLISHED'})
WHERE a.deleted_at IS NULL AND a.image IS NOT NULL
RETURN a.title AS titulo, a.image AS imagen ORDER BY a.post_date DESC;

// 15. Autores mas populares: likes recibidos en todos sus articulos
MATCH (f:User)-[:LIKED]->(a:Article {status: 'PUBLISHED'})<-[:WROTE]-(u:User)
WHERE f.deleted_at IS NULL AND a.deleted_at IS NULL AND u.deleted_at IS NULL
RETURN u.name AS autor, count(*) AS likes ORDER BY likes DESC LIMIT 5;
