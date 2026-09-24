from app.Services.bill_service import get_bill, get_recent_bills


bills = get_recent_bills(5)

for bill in bills:
    print(bill)

bill_id = bills[0][0]

result = get_bill(bill_id)

print("\nBill:")
print(result["bill"])

print("\nItems:")
for item in result["items"]:
    print(item)