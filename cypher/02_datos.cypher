// Datos de prueba del blog. Borra todo lo anterior y vuelve a cargar.
MATCH (n) DETACH DELETE n;

// Usuarios. Contraseña de los tres: Blog2026! (guardada como hash scrypt, igual que en la app).
// avatar y cover (fotos de perfil y portada) se agregan desde la app, en "Editar perfil".
CREATE (:User {user_id: 1, name: 'Ana Torres',    email: 'ana.torres@correo.com',    role: 'ADMIN',  password_hash: 'scrypt$f812552d5fa8141d2c532dc8563fc706$147354b6f7cfba37f2b3a72123ad5e588d5ccfa76924f7e7c8ffa71912bfcae8fef598ff14f73ec48c0cff83428ec4a4e39f208b7547c12e6cd1eaa77744a465', created_at: localdatetime('2026-11-01T09:00:00')});
CREATE (:User {user_id: 2, name: 'Luis Moreno',   email: 'luis.moreno@correo.com',   role: 'AUTHOR', password_hash: 'scrypt$b317e12888c42f6e64b48bbcdfb3b1b6$4bf220ea85d38e0ecb3f092a35d63f70cfd9577b6701ea600982bcf1933e3dbaeaa4d0033960b3318f19024c0fe730dea60a9e97d032fc397304085fe02ac87b', created_at: localdatetime('2026-11-02T10:30:00')});
CREATE (:User {user_id: 3, name: 'Sofia Ramirez', email: 'sofia.ramirez@correo.com', role: 'AUTHOR', password_hash: 'scrypt$847640bac6440a418e17689b0111a48b$0e91a780ddf4f392604c6f9c0d9a5e50e581558db97d69ad698d08b69b5d66d0762af89942793fd8e450bd190b53119b6282bd1db8e291714d50cc3f487dae9e', created_at: localdatetime('2026-11-03T16:15:00')});

// Etiquetas
CREATE (:Tag {tag_id: 1, name: 'neo4j',    url: 'neo4j'});
CREATE (:Tag {tag_id: 2, name: 'cypher',   url: 'cypher'});
CREATE (:Tag {tag_id: 3, name: 'grafos',   url: 'grafos'});
CREATE (:Tag {tag_id: 4, name: 'modelado', url: 'modelado'});
CREATE (:Tag {tag_id: 5, name: 'python',   url: 'python'});

// Categorias
CREATE (:Category {category_id: 1, name: 'Tutoriales', url: 'tutoriales'});
CREATE (:Category {category_id: 2, name: 'Avanzado',   url: 'avanzado'});
CREATE (:Category {category_id: 3, name: 'Noticias',   url: 'noticias'});

// Articulos, cada uno unido a su autor con WROTE (1 a N)
MATCH (u:User {user_id: 1})
CREATE (u)-[:WROTE]->(:Article {article_id: 1, title: 'Que es una base de datos de grafos', status: 'PUBLISHED',
  post_date: localdatetime('2026-11-05T12:00:00'),
  body_text: 'Una base de datos de grafos guarda nodos y relaciones.\n\nEn lugar de tablas y llaves foraneas, cada relacion se guarda directo entre los dos nodos. Por eso preguntar quien escribio un articulo o que etiquetas tiene es solo seguir una flecha.\n\nEn este blog los usuarios, articulos, comentarios, etiquetas y categorias son nodos.'});
MATCH (u:User {user_id: 2})
CREATE (u)-[:WROTE]->(:Article {article_id: 2, title: 'Primeros pasos con Cypher', status: 'PUBLISHED',
  post_date: localdatetime('2026-11-10T18:20:00'),
  body_text: 'Cypher es el lenguaje de consultas de Neo4j.\n\nSe dibujan los patrones con parentesis para los nodos y flechas para las relaciones, por ejemplo (u:User)-[:WROTE]->(a:Article).\n\nCon MATCH se busca, con CREATE se crea, con SET se cambia y con DETACH DELETE se borra un nodo junto con sus relaciones.'});
MATCH (u:User {user_id: 2})
CREATE (u)-[:WROTE]->(:Article {article_id: 3, title: 'Relaciones N a N sin tabla intermedia', status: 'DRAFT',
  post_date: localdatetime('2026-11-15T08:45:00'),
  body_text: 'En SQL un articulo con varias etiquetas necesita una tabla puente.\n\nEn Neo4j solo se crea una relacion TAGGED por cada etiqueta. Si se borra la etiqueta con DETACH DELETE, sus relaciones se van con ella y no queda basura.'});

// Etiquetas y categorias de cada articulo (N a N)
MATCH (a:Article {article_id: 1}), (t:Tag) WHERE t.name IN ['neo4j', 'grafos'] CREATE (a)-[:TAGGED]->(t);
MATCH (a:Article {article_id: 2}), (t:Tag) WHERE t.name IN ['neo4j', 'cypher'] CREATE (a)-[:TAGGED]->(t);
MATCH (a:Article {article_id: 3}), (t:Tag) WHERE t.name IN ['grafos', 'modelado'] CREATE (a)-[:TAGGED]->(t);
MATCH (a:Article {article_id: 1}), (c:Category {name: 'Tutoriales'}) CREATE (a)-[:IN_CATEGORY]->(c);
MATCH (a:Article {article_id: 2}), (c:Category) WHERE c.name IN ['Tutoriales', 'Avanzado'] CREATE (a)-[:IN_CATEGORY]->(c);
MATCH (a:Article {article_id: 3}), (c:Category {name: 'Avanzado'}) CREATE (a)-[:IN_CATEGORY]->(c);

// Comentarios: ON apunta al articulo (1 a N) y POSTED sale del usuario (1 a N).
// El comentario 2 no tiene POSTED: es de una cuenta que ya se borro.
MATCH (a:Article {article_id: 1}), (u:User {user_id: 2})
CREATE (u)-[:POSTED]->(:Comment {comment_id: 1, name: 'Luis Moreno', body_text: 'Muy claro, sobre todo lo de seguir la flecha.', created_at: localdatetime('2026-11-06T09:10:00')})-[:ON]->(a);
MATCH (a:Article {article_id: 1})
CREATE (:Comment {comment_id: 2, name: 'Visitante', url: 'https://blog-invitado.example.com', body_text: 'Llegue buscando la diferencia con SQL y me sirvio.', created_at: localdatetime('2026-11-07T20:00:00')})-[:ON]->(a);
MATCH (a:Article {article_id: 1}), (u:User {user_id: 3})
CREATE (u)-[:POSTED]->(:Comment {comment_id: 3, name: 'Sofia Ramirez', body_text: 'Estaria bien un ejemplo con recomendaciones.', created_at: localdatetime('2026-11-08T11:30:00')})-[:ON]->(a);
MATCH (a:Article {article_id: 2}), (u:User {user_id: 1})
CREATE (u)-[:POSTED]->(:Comment {comment_id: 4, name: 'Ana Torres', body_text: 'El DETACH DELETE era justo lo que no me salia. Gracias.', created_at: localdatetime('2026-11-11T13:05:00')})-[:ON]->(a);

// Likes: (:User)-[:LIKED]->(:Article), solo en articulos publicados
MATCH (u:User), (a:Article) WHERE [u.user_id, a.article_id] IN [[2, 1], [3, 1], [1, 2], [3, 2]]
CREATE (u)-[:LIKED {at: localdatetime('2026-11-12T10:00:00')}]->(a);

// Contadores para que la app siga dando ids despues de estos
UNWIND [['User', 3], ['Article', 3], ['Comment', 4], ['Tag', 5], ['Category', 3]] AS pair
MERGE (c:Counter {name: pair[0]}) SET c.value = pair[1];
