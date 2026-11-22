from app.common.taxonomy_service import TaxonomyService


class TagsService(TaxonomyService):
    label, key, relationship, noun = "Tag", "tag_id", "TAGGED", "etiqueta"
