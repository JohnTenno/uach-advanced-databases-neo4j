from app.common.taxonomy_controller import taxonomy_blueprint
from app.modules.tags.tags_service import TagsService

tags = taxonomy_blueprint("tags", TagsService(), "Etiquetas")
