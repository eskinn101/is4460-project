"""
Test script to verify USDA Food Data Central API integration with health variables.
"""

import os
import requests
from typing import Dict, Any

def get_usda_api_key() -> str | None:
    """Get USDA API key from environment."""
    return os.getenv("FOOD_DATA_GOV")

def search_foods_by_query(query: str, pageSize: int = 5) -> Dict[str, Any]:
    """
    Search USDA FDC database by query string.
    Typical health-related queries: 'chicken', 'brown rice', 'greek yogurt', 'eggs', etc.
    """
    api_key = get_usda_api_key()
    if not api_key:
        return {"error": "USDA_FOOD_GOV API key not set"}
    
    url = "https://api.nal.usda.gov/fdc/v1/foods/search"
    params = {
        "query": query,
        "pageSize": pageSize,
        "api_key": api_key,
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"API request failed: {str(e)}"}

def test_health_variable_query(meal_name: str, target_calories: int | None = None) -> Dict[str, Any]:
    """
    Test USDA API with a health-related query.
    
    Args:
        meal_name: Name of food to search (e.g., "greek yogurt")
        target_calories: Optional target calorie range (not yet used but can filter results)
    
    Returns:
        API response with food nutritional data
    """
    result = search_foods_by_query(meal_name)
    
    if "error" in result:
        return result
    
    foods = result.get("foods", [])
    if not foods:
        return {"message": f"No foods found for '{meal_name}'"}
    
    # Format relevant nutrition data for health tracking
    formatted = {
        "query": meal_name,
        "found_count": len(foods),
        "foods": []
    }
    
    for food in foods[:3]:  # Top 3 results
        nutrients = {}
        for nutrient in food.get("foodNutrients", []):
            # Extract key health variables
            if nutrient.get("nutrientName") in ["Energy", "Protein", "Carbohydrate", "Total lipid (fat)", "Sugars"]:
                nutrients[nutrient["nutrientName"]] = {
                    "value": nutrient.get("value"),
                    "unit": nutrient.get("unitName")
                }
        
        formatted["foods"].append({
            "fdcId": food.get("fdcId"),
            "description": food.get("description"),
            "dataType": food.get("dataType"),
            "nutrients": nutrients,
            "servingSize": food.get("servingSizeUnit")
        })
    
    return formatted

if __name__ == "__main__":
    print("=" * 60)
    print("USDA Food API Test - Health Variable Query")
    print("=" * 60)
    
    api_key = get_usda_api_key()
    print(f"\n✓ API Key Status: {'SET ✓' if api_key else '❌ NOT SET'}")
    
    if not api_key:
        print("\n⚠️  To enable this test, set the FOOD_DATA_GOV environment variable")
        print("   Get a free key at: https://api.nal.usda.gov/fdc/")
        exit(1)
    
    # Test with common health-tracked foods
    test_queries = [
        "greek yogurt",  # protein source
        "brown rice",    # carb source
        "chicken breast", # lean protein
    ]
    
    for query in test_queries:
        print(f"\n{'─' * 60}")
        print(f"Testing query: '{query}'")
        print('─' * 60)
        result = test_health_variable_query(query)
        
        if "error" in result:
            print(f"❌ Error: {result['error']}")
        elif "message" in result:
            print(f"⚠️  {result['message']}")
        else:
            print(f"✓ Found {result['found_count']} foods")
            for i, food in enumerate(result["foods"], 1):
                print(f"\n  [{i}] {food['description'][:50]}...")
                if food["nutrients"]:
                    for nutrient_name, nutrient_data in food["nutrients"].items():
                        if nutrient_data["value"]:
                            print(f"      • {nutrient_name}: {nutrient_data['value']} {nutrient_data['unit']}")
    
    print("\n" + "=" * 60)
    print("✓ USDA API Test Complete")
    print("=" * 60)
