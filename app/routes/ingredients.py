from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db

router = APIRouter(prefix="/api/ingredients", tags=["Ingredients"])

@router.get("/")
def get_ingredients(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    offset = (page-1)*limit
    cursor= db.connection().connection.cursor()

    cursor.execute(
        """
        SELECT
            i.id,
            i.name,
            COUNT(pi.product_id) as product_count
        FROM ingredients i
        LEFT JOIN product_ingredients pi ON i.id = pi.ingredient_id
        GROUP BY i.id, i.name
        ORDER BY product_count DESC
        LIMIT %s OFFSET %s
        """,
        (limit, offset)
    )

    ingredients = [
        {
            "id": row[0],
            "name": row[1],
            "product_count": row[2]
        }
        for row in cursor.fetchall()
    ]

    return {"ingredients": ingredients}

@router.get("/{ingredient_id}")
def get_ingredient_detail(ingredient_id: int, db: Session = Depends(get_db)):
    """
    Get ingredient details and products containing it
    """
    cursor = db.connection().connection.cursor()
    
    cursor.execute(
        "SELECT id, name, description FROM ingredients WHERE id = %s",
        (ingredient_id,)
    )
    ingredient = cursor.fetchone()
    
    if not ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    
    cursor.execute(
        """
        SELECT p.id, p.name, p.brand, p.category, p.rating, p.image_url
        FROM products p
        JOIN product_ingredients pi ON p.id = pi.product_id
        WHERE pi.ingredient_id = %s
        ORDER BY p.rating DESC NULLS LAST
        """,
        (ingredient_id,)
    )
    
    products = [
        {
            "id": row[0],
            "name": row[1],
            "brand": row[2],
            "category": row[3],
            "rating": row[4],
            "image_url": row[5]
        }
        for row in cursor.fetchall()
    ]
    
    return {
        "ingredient": {
            "id": ingredient[0],
            "name": ingredient[1],
            "description": ingredient[2]
        },
        "product_count": len(products),
        "products": products
    }

@router.get("/trending/top")
def get_trending_ingredients(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get most popular ingredients by product count
    """
    cursor = db.connection().connection.cursor()
    
    cursor.execute(
        """
        SELECT 
            i.id,
            i.name,
            COUNT(pi.product_id) as product_count
        FROM ingredients i
        JOIN product_ingredients pi ON i.id = pi.ingredient_id
        GROUP BY i.id, i.name
        HAVING COUNT(pi.product_id) > 1
        ORDER BY product_count DESC
        LIMIT %s
        """,
        (limit,)
    )
    
    trending = [
        {
            "id": row[0],
            "name": row[1],
            "product_count": row[2]
        }
        for row in cursor.fetchall()
    ]
    
    return {"trending_ingredients": trending}