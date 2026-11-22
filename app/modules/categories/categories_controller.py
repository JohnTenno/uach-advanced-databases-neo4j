from app.common.taxonomy_controller import taxonomy_blueprint
from app.modules.categories.categories_service import CategoriesService

categories = taxonomy_blueprint("categories", CategoriesService(), "Categorías")
