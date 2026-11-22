from app.common.taxonomy_service import TaxonomyService


class CategoriesService(TaxonomyService):
    label, key, relationship, noun = "Category", "category_id", "IN_CATEGORY", "categoría"
