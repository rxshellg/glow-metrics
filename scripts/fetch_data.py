import os
import re
import time
import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def fetch_products_from_api(category, page_size=100):
    url = f"https://world.openbeautyfacts.org/category/{category}.json"
    params = {"page_size": page_size}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json().get('products', [])
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {category}: {e}")
        return []
    
def clean_product_data(product):
    name = product.get('product_name', '').strip()
    brand = product.get('brands', '').strip()

    if brand:
        brand = ' '.join(word.capitalize() for word in brand.split())

    return {
        'name': name[:255] if name else None,
        'brand': brand[:100] if brand else None,
        'category': product.get('categories_tags', ['Unknown'])[0][:100] if product.get('categories_tags') else 'Unknown',
        'price': None,
        'rating': None,
        'review_count': None,
        'image_url': product.get('image_url'),
        'product_url': product.get('url'),
        'ingredients_text': product.get('ingredients_text', '').strip()
    }

def clean_ingredient_name(name):
    if not name: return None
    
    name = name.strip().rstrip('.*').replace('*', '')

    if '/' in name:
        name = name.split('/')[0].strip()
    
    if '(' in name and not name.startswith('('):
        name = re.sub(r'\([^)]*\)', '', name).strip()

    if not name or len(name) > 100 or ',' in name:
        return None

    return ' '.join(word.capitalize() for word in name.split())

def insert_or_get_ingredient(cursor, ingredient_name):
    ingredient_name = clean_ingredient_name(ingredient_name)

    if not ingredient_name:
        return None
    
    # Try to insert, if exists get the id
    cursor.execute(
        """
        INSERT INTO ingredients (name)
        VALUES (%s)
        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
        """,
        (ingredient_name,)
    )
    return cursor.fetchone()[0]

def insert_product(cursor, product_data):
    cursor.execute(
        """
        INSERT INTO products (name, brand, category, price, rating, review_count, image_url, product_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            product_data['name'],
            product_data['brand'],
            product_data['category'],
            product_data['price'],
            product_data['rating'],
            product_data['review_count'],
            product_data['image_url'],
            product_data['product_url']
        )
    )

    product_id = cursor.fetchone()[0]

    # Process ingredients
    ingredients_text = product_data['ingredients_text']
    if ingredients_text:
        ingredient_list = [
            ing.strip()
            for ing in ingredients_text.split(',')
            if ing.strip()
        ]

        # Insert each ingredient and link to product
        for position, ingredient_name in enumerate(ingredient_list, start=1):
            ingredient_id = insert_or_get_ingredient(cursor, ingredient_name)

            if ingredient_id:
                cursor.execute(
                    """
                    INSERT INTO product_ingredients (product_id, ingredient_id, position)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (product_id, ingredient_id, position)
                )

    return product_id

def main():
    # Categories to fetch
    categories = [
        'facial-creams',
        'moisturizers',
        'serum',
        'cleansers',
        'face-masks',
        'sunscreen',
        'eye-cream',
        'toner',
        'lip-balms',
        'body-oils',
        'day-creams',
        'anti-wrinkles-creams',
        'aftershaves',
        'micellar-water',
        'body-wash',
        'night-creams',
        'face-scrubs',
        'cleansing-milks',
        'body-scrubs'
    ]

    conn = get_db_connection()
    cursor = conn.cursor()

    total_inserted = 0

    try:
        for category in categories:
            print(f"\nFetching {category}...")
            products = fetch_products_from_api(category, page_size=50)

            inserted_count = 0
            for product in products:
                try:
                    product_data = clean_product_data(product)

                    if not product_data['name'] or not product_data['brand'] or not product_data['ingredients_text']:
                        continue

                    product_id = insert_product(cursor, product_data)
                    inserted_count += 1

                    if inserted_count % 10 == 0:
                        print(f"Inserted {inserted_count} products")
                    
                except Exception as e:
                    print(f"Error inserting product: {e}")
                    continue

            conn.commit()
            total_inserted += inserted_count
            print(f"Completed {category}: {inserted_count} products")

            time.sleep(1)

        print(f"\nData import complete. Total products: {total_inserted}")

        cursor.execute("""
            SELECT
                (SELECT COUNT(*) FROM products) as product_count,
                (SELECT COUNT(*) FROM ingredients) as ingredient_count,
                (SELECT COUNT(*) FROM product_ingredients) as relationship_count
        """)
        product_count, ingredient_count, relationship_count = cursor.fetchone()

        print("\nDatabase summary:")
        print(f"Products: {product_count}")
        print(f"Unique ingredients: {ingredient_count}")
        print(f"Product-Ingredient relationships: {relationship_count}")

    except Exception as e:
        print(f"\nError: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    main()