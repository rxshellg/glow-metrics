from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app.database import get_db
from typing import Optional

router = APIRouter(prefix="/api/admin", tags=["Admin"])

@router.delete("/ingredients/{ingredient_id}")
def delete_ingredient(ingredient_id: int, db: Session = Depends(get_db)):
    """
    Delete an ingredient and all its relationships
    
    This will remove the ingredient from all products that contain it.
    """
    cursor = db.connection().connection.cursor()
    
    cursor.execute("SELECT id, name FROM ingredients WHERE id = %s", (ingredient_id,))
    ingredient = cursor.fetchone()
    
    if not ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    
    ingredient_name = ingredient[1]
    
    cursor.execute(
        "SELECT COUNT(DISTINCT product_id) FROM product_ingredients WHERE ingredient_id = %s",
        (ingredient_id,)
    )
    affected_products = cursor.fetchone()[0]
    
    cursor.execute(
        "DELETE FROM product_ingredients WHERE ingredient_id = %s",
        (ingredient_id,)
    )
    
    cursor.execute("DELETE FROM ingredients WHERE id = %s", (ingredient_id,))
    
    db.connection().connection.commit()
    
    return {
        "message": f"Deleted ingredient '{ingredient_name}'",
        "ingredient_id": ingredient_id,
        "affected_products": affected_products
    }


@router.post("/ingredients/{old_id}/merge/{new_id}")
def merge_ingredients(
    old_id: int, 
    new_id: int, 
    db: Session = Depends(get_db)
):
    """
    Merge two ingredients: move all products from old_id to new_id, then delete old_id
    """
    cursor = db.connection().connection.cursor()
    
    cursor.execute("SELECT id, name FROM ingredients WHERE id IN (%s, %s)", (old_id, new_id))
    ingredients = cursor.fetchall()
    
    if len(ingredients) != 2:
        raise HTTPException(status_code=404, detail="One or both ingredients not found")
    
    old_name = next(ing[1] for ing in ingredients if ing[0] == old_id)
    new_name = next(ing[1] for ing in ingredients if ing[0] == new_id)
    
    cursor.execute(
        "SELECT COUNT(DISTINCT product_id) FROM product_ingredients WHERE ingredient_id = %s",
        (old_id,)
    )
    old_product_count = cursor.fetchone()[0]

    cursor.execute(
        """
        DELETE FROM product_ingredients
        WHERE ingredient_id = %s
        AND product_id IN (
            SELECT product_id 
            FROM product_ingredients 
            WHERE ingredient_id = %s
        )
        """,
        (old_id, new_id)
    )
    
    cursor.execute(
        """
        UPDATE product_ingredients
        SET ingredient_id = %s
        WHERE ingredient_id = %s
        """,
        (new_id, old_id)
    )
    
    cursor.execute("DELETE FROM ingredients WHERE id = %s", (old_id,))
    
    db.connection().connection.commit()
    
    return {
        "message": f"Merged '{old_name}' into '{new_name}'",
        "old_id": old_id,
        "new_id": new_id,
        "old_name": old_name,
        "new_name": new_name,
        "products_affected": old_product_count
    }


@router.put("/ingredients/{ingredient_id}")
def rename_ingredient(
    ingredient_id: int,
    new_name: str = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    cursor = db.connection().connection.cursor()

    cursor.execute("SELECT id, name FROM ingredients WHERE id = %s", (ingredient_id,))
    ingredient = cursor.fetchone()
    
    if not ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    
    old_name = ingredient[1]

    cursor.execute("SELECT id FROM ingredients WHERE name = %s AND id != %s", (new_name, ingredient_id))
    existing = cursor.fetchone()
    
    if existing:
        raise HTTPException(
            status_code=400, 
            detail=f"Ingredient '{new_name}' already exists with ID {existing[0]}. Use merge endpoint instead."
        )
    
    cursor.execute(
        "UPDATE ingredients SET name = %s WHERE id = %s",
        (new_name, ingredient_id)
    )
    
    db.connection().connection.commit()
    
    return {
        "message": f"Renamed '{old_name}' to '{new_name}'",
        "ingredient_id": ingredient_id,
        "old_name": old_name,
        "new_name": new_name
    }

@router.post("/ingredients/bulk-merge")
def bulk_merge_by_name(
    search_pattern: str = Body(..., embed=True),
    keep_name: str = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    """
    Merge all ingredients matching a pattern into one standard name
    """
    cursor = db.connection().connection.cursor()
    
    cursor.execute(
        """
        INSERT INTO ingredients (name)
        VALUES (%s)
        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
        """,
        (keep_name,)
    )
    keep_id = cursor.fetchone()[0]
    
    cursor.execute(
        "SELECT id, name FROM ingredients WHERE name ILIKE %s AND id != %s",
        (f"%{search_pattern}%", keep_id)
    )
    to_merge = cursor.fetchall()
    
    if not to_merge:
        return {
            "message": "No matching ingredients found",
            "pattern": search_pattern,
            "keep_name": keep_name,
            "merged_count": 0
        }
    
    merged_names = []
    total_products_affected = 0
    
    for ingredient_id, ingredient_name in to_merge:
        cursor.execute(
            "SELECT COUNT(DISTINCT product_id) FROM product_ingredients WHERE ingredient_id = %s",
            (ingredient_id,)
        )
        product_count = cursor.fetchone()[0]
        total_products_affected += product_count
        
        cursor.execute(
            """
            UPDATE product_ingredients
            SET ingredient_id = %s
            WHERE ingredient_id = %s
            """,
            (keep_id, ingredient_id)
        )
        
        cursor.execute(
            """
            DELETE FROM product_ingredients
            WHERE id IN (
                SELECT id FROM (
                    SELECT id, ROW_NUMBER() OVER (PARTITION BY product_id, ingredient_id ORDER BY id) as rn
                    FROM product_ingredients
                    WHERE ingredient_id = %s
                ) t
                WHERE rn > 1
            )
            """,
            (keep_id,)
        )
        
        cursor.execute("DELETE FROM ingredients WHERE id = %s", (ingredient_id,))
        
        merged_names.append(ingredient_name)
    
    db.connection().connection.commit()
    
    return {
        "message": f"Merged {len(merged_names)} ingredients into '{keep_name}'",
        "pattern": search_pattern,
        "keep_name": keep_name,
        "keep_id": keep_id,
        "merged_count": len(merged_names),
        "merged_ingredients": merged_names,
        "total_products_affected": total_products_affected
    }