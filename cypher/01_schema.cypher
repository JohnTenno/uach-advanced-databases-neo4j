// Esquema del blog en Neo4j: ids unicos y campos que no se pueden repetir.
CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE;
CREATE CONSTRAINT user_email IF NOT EXISTS FOR (u:User) REQUIRE u.email IS UNIQUE;
CREATE CONSTRAINT article_id IF NOT EXISTS FOR (a:Article) REQUIRE a.article_id IS UNIQUE;
CREATE CONSTRAINT comment_id IF NOT EXISTS FOR (c:Comment) REQUIRE c.comment_id IS UNIQUE;
CREATE CONSTRAINT tag_id IF NOT EXISTS FOR (t:Tag) REQUIRE t.tag_id IS UNIQUE;
CREATE CONSTRAINT tag_name IF NOT EXISTS FOR (t:Tag) REQUIRE t.name IS UNIQUE;
CREATE CONSTRAINT tag_url IF NOT EXISTS FOR (t:Tag) REQUIRE t.url IS UNIQUE;
CREATE CONSTRAINT category_id IF NOT EXISTS FOR (c:Category) REQUIRE c.category_id IS UNIQUE;
CREATE CONSTRAINT category_name IF NOT EXISTS FOR (c:Category) REQUIRE c.name IS UNIQUE;
CREATE CONSTRAINT category_url IF NOT EXISTS FOR (c:Category) REQUIRE c.url IS UNIQUE;
CREATE CONSTRAINT counter_name IF NOT EXISTS FOR (c:Counter) REQUIRE c.name IS UNIQUE;
CREATE INDEX article_date IF NOT EXISTS FOR (a:Article) ON (a.post_date);
