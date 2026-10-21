
menu = [
    {"name": "Chicken Biryani", "price": 150, "qty": 5},
    {"name": "Daal Chawal", "price": 90, "qty": 8},
    {"name": "Chicken Karahi", "price": 250, "qty": 10},
    {"name": "Raita", "price": 30, "qty": 10},
    {"name": "Gulab Jamun", "price": 60, "qty": 6},
]


def get_menu_text():
    lines = []
    available_dishes = [
        dish for dish in menu if dish["qty"] > 0
    ]

    for i, dish in enumerate(available_dishes, start=1):
        lines.append(
            f'{i}. {dish["name"]} - Rs {dish["price"]} '
            f'({dish["qty"]} left)'
        )

    return "\n".join(lines)


def place_order(dish_number, qty):
    available_dishes = [
        dish for dish in menu if dish["qty"] > 0
    ]

    if dish_number < 1 or dish_number > len(available_dishes):
        return "Invalid dish number. Please check the menu."

    if qty < 1:
        return "Quantity must be at least 1."

    dish = available_dishes[dish_number - 1]

    if qty > dish["qty"]:
        return f'Only {dish["qty"]} {dish["name"]} available.'

    dish["qty"] -= qty
    total = dish["price"] * qty

    return (
        f'{qty} x {dish["name"]} ordered. '
        f'Total: Rs {total}'
    )


conversations = {}


def handle_message(phone, text):
    if phone not in conversations:
        conversations[phone] = {"step": "choosing"}
        return (
            "Welcome to Annvitra!\n"
            "Today's menu:\n"
            f"{get_menu_text()}\n"
            "Send dish number and quantity, e.g. 1 2"
        )

    parts = text.strip().split()

    if len(parts) != 2:
        return "Please send dish number and quantity, e.g. 1 2"

    try:
        dish_number = int(parts[0])
        qty = int(parts[1])
    except ValueError:
        return "Please use numbers, e.g. 1 2"

    return place_order(dish_number, qty)


if __name__ == "__main__":
    print(handle_message("9230000", "hi"))
    print(handle_message("9230000", "1 2"))
    print(get_menu_text())
