from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db

router = APIRouter(prefix="/api/products", tags=["Products"])

@router.get("/")
def get_products(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    brand: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    offset = (page-1)*limit
    query = "SELECT id, name, brand, category, price, rating, image_url FROM products WHERE 1=1"
    params = []

    if brand:
        query += " AND brand ILIKE %s"
        params.append(f"%{brand}%")

    if category:
        query += " AND category ILIKE %s"
        params.append(f"%{category}%")

    query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    cursor = db.connection().connection.cursor()
    cursor.execute(query, params)

    columns = [desc[0] for desc in cursor.description]
    products = [dict(zip(columns, row)) for row in cursor.fetchall()]

    count_query = "SELECT COUNT(*) FROM products WHERE 1=1"
    count_params = []

    if brand:
        count_query += " AND brand ILIKE %s"
        count_params.append(f"%{brand}%")
    if category:
        count_query += " AND category ILIKE %s"
        count_params.append(f"%{category}%")

    cursor.execute(count_query, count_params)
    total = cursor.fetchone()[0]

    return {
        "products": products,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit
        }
    }

@router.get("/{product_id}")
def get_product_detail(product_id: int, db: Session = Depends(get_db)):
    cursor = db.connection().connection.cursor()

    cursor.execute(
        "SELECT * FROM products WHERE id = %s",
        (product_id,)
    )
    product = cursor.fetchone()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    columns = [desc[0] for desc in cursor.description]
    product_dict = dict(zip(columns, product))

    cursor.execute(
        """
        SELECT i.id, i.name, pi.position
        FROM ingredients i
        JOIN product_ingredients pi ON i.id = pi.ingredient_id
        WHERE pi.product_id = %s
        ORDER BY pi.position
        """,
        (product_id,)
    )

    ingredients = [
        {"id": row[0], "name": row[1], "position": row[2]}
        for row in cursor.fetchall()
    ]

    product_dict['ingredients'] = ingredients

    return product_dict

@router.get("/search/by-ingredient")
def search_by_ingredient(
    ingredient: str = Query(..., min_length=2),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Find products containing a specific ingredient
    """
    cursor = db.connection().connection.cursor()

    cursor.execute(
        """
        SELECT DISTINCT p.id, p.name, p.brand, p.category, p.rating, p.image_url
        FROM products p
        JOIN product_ingredients pi ON p.id = pi.product_id
        JOIN ingredients i ON pi.ingredient_id = i.id
        WHERE i.name ILIKE %s
        ORDER BY p.rating DESC NULLS LAST
        LIMIT %s
        """,
        (f"%{ingredient}%", limit)
    )

    columns = [desc[0] for desc in cursor.description]
    products = [dict(zip(columns, row)) for row in cursor.fetchall()]

    return {
        "query": ingredient,
        "count": len(products),
        "products": products
    }