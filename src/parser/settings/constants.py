from typing import List

COLUMNS: List[str] = [
    "url", "name",
    "price_rub", "weight_g",
    "kcal_per_100g", "proteins_g_per_100g", "fats_g_per_100g", "carbs_g_per_100g",
    "shelf_life_days", "storage_temp_min_c", "storage_temp_max_c",
    "category_main", "category_path",
    "brand", "country", "manufacturer",
    "rating", "ratings_count",
    "ingredients",
    "tags", "image_path",
]

NUMERIC_COLUMNS: List[str] = [
    "price_rub", "weight_g",
    "kcal_per_100g", "proteins_g_per_100g", "fats_g_per_100g", "carbs_g_per_100g",
    "shelf_life_days", "storage_temp_min_c", "storage_temp_max_c",
    "rating", "ratings_count",
]

STRING_COLUMNS: List[str] = ["url", "name", "category_path", "manufacturer", "ingredients","tags", "image_path"]
CATEGORICAL_COLUMNS: List[str] = ["category_main", "brand", "country"]


BASE_CATEGORY_URL: str = "https://vkusvill.ru/goods/gotovaya-eda/"
MAX_PAGES: int = 60
