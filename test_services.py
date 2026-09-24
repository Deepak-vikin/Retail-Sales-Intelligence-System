from app.Services.product_service import get_products
from app.Services.inventory_service import get_inventory, get_low_stock_products
from app.Services.supplier_service import get_suppliers
from app.Services.purchase_service import get_purchases
from app.Services.bill_service import get_recent_bills
from app.Services.analytics_service import (
    get_total_revenue, get_total_units_sold, get_total_bills, get_average_bill_value,
    get_sales_by_product, get_sales_by_category, get_sales_for_date_range, get_sales_by_payment_mode
)

def test_database_services():
    print("Testing Database Services...")
    
    products = get_products()
    print(f"1. Number of products: {len(products)} (Expected: 73)")
    
    inventory = get_inventory()
    print(f"2. Number of inventory records: {len(inventory)} (Expected: 73)")
    
    suppliers = get_suppliers()
    print(f"3. Number of suppliers: {len(suppliers)} (Expected: 12)")
    
    purchases = get_purchases()
    print(f"4. Number of purchases: {len(purchases)} (Expected: 1223)")
    
    total_bills = get_total_bills()
    print(f"5. Number of bills: {total_bills} (Expected: 72156)")
    
    from app.core.database import connection
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM bill_items;")
        bill_items_count = cursor.fetchone()[0]
        print(f"6. Number of bill_items: {bill_items_count} (Expected: 205212)")
    finally:
        conn.close()
        
    low_stock = get_low_stock_products()
    print(f"7. Low-stock query works: {len(low_stock)} products found")
    
    revenue = get_total_revenue()
    print(f"8. Total revenue query works: {revenue}")
    
    units = get_total_units_sold()
    print(f"9. Total units sold works: {units}")
    
    print(f"10. Total bills check again: {total_bills}")
    
    avg_bill = get_average_bill_value()
    print(f"11. Average bill value works: {avg_bill}")
    
    product_sales = get_sales_by_product()
    print(f"12. Product sales query works: {len(product_sales)} products found")
    
    cat_sales = get_sales_by_category()
    print(f"13. Category sales query works: {len(cat_sales)} categories found")
    
    date_sales = get_sales_for_date_range('2023-01-01', '2026-12-31')
    print(f"14. Date-range sales query works: {date_sales}")
    
    payment_sales = get_sales_by_payment_mode()
    print(f"15. Payment-mode sales query works: {len(payment_sales)} modes found")
    
    print("All tests executed successfully.")

if __name__ == "__main__":
    test_database_services()
