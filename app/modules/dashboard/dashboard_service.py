from app.database import read, read_one


class DashboardService:
    def totals(self) -> dict:
        """Only live nodes count; logically deleted ones are left out."""
        return read_one("""
            RETURN COUNT { (u:User) WHERE u.deleted_at IS NULL } AS users,
                   COUNT { (a:Article) WHERE a.deleted_at IS NULL } AS articles,
                   COUNT { (a:Article {status: 'PUBLISHED'}) WHERE a.deleted_at IS NULL } AS published,
                   COUNT { (c:Comment) WHERE c.deleted_at IS NULL } AS comments,
                   COUNT { (u:User)-[:LIKED]->(a:Article) WHERE u.deleted_at IS NULL AND a.deleted_at IS NULL } AS likes,
                   COUNT { (t:Tag) WHERE t.deleted_at IS NULL } AS tags,
                   COUNT { (c:Category) WHERE c.deleted_at IS NULL } AS categories,
                   COUNT { (x)-[]->(y) WHERE x.deleted_at IS NULL AND y.deleted_at IS NULL } AS relationships""")
