from abc import ABC, abstractmethod

# --- 1. Decorator & Component Pattern (Menu Customization) ---
class Beverage(ABC):
    @abstractmethod
    def get_description(self) -> str: pass
    @abstractmethod
    def cost(self) -> float: pass
    @abstractmethod
    def get_required_ingredients(self) -> list: pass

class ConcreteProduct(Beverage):
    def __init__(self, menu_item):
        self.menu_item = menu_item
        
    def get_description(self) -> str: return self.menu_item.name
    def cost(self) -> float: return float(self.menu_item.price)
    
    def get_required_ingredients(self) -> list:
        # Dynamic Recipe Model integration (No hardcoded string matching)
        ingredients = []
        for r in self.menu_item.recipe_items.select_related('ingredient').all():
            ingredients.append((r.ingredient.name, r.quantity_required))
        return ingredients

class BeverageDecorator(Beverage):
    def __init__(self, beverage: Beverage): self._beverage = beverage
    def get_required_ingredients(self) -> list:
        return self._beverage.get_required_ingredients()

class TemperatureDecorator(BeverageDecorator):
    def __init__(self, beverage: Beverage, temp: str):
        super().__init__(beverage)
        self.temp = temp
    def get_description(self) -> str:
        return f"{self._beverage.get_description()} ({self.temp})"
    def cost(self) -> float:
        return self._beverage.cost()

class SweetnessDecorator(BeverageDecorator):
    def __init__(self, beverage: Beverage, sweetness: str):
        super().__init__(beverage)
        self.sweetness = sweetness
    def get_description(self) -> str:
        return f"{self._beverage.get_description()} [หวาน {self.sweetness}]"
    def cost(self) -> float:
        return self._beverage.cost()

class Milk(BeverageDecorator):
    def get_description(self) -> str: return f"{self._beverage.get_description()} (+Milk)"
    def cost(self) -> float: return self._beverage.cost() + 15.0
    def get_required_ingredients(self) -> list:
        return self._beverage.get_required_ingredients() + [('Milk', 1)]

class Syrup(BeverageDecorator):
    def get_description(self) -> str: return f"{self._beverage.get_description()} (+Syrup)"
    def cost(self) -> float: return self._beverage.cost() + 10.0
    def get_required_ingredients(self) -> list:
        return self._beverage.get_required_ingredients() + [('Syrup', 1)]

# --- FEATURE 1: Composite Pattern (Shopping Cart) ---
class OrderCart(Beverage):
    def __init__(self):
        self._items = []
        
    def add_item(self, beverage: Beverage):
        self._items.append(beverage)
        
    def get_description(self) -> str:
        return " | ".join([item.get_description() for item in self._items])
        
    def cost(self) -> float:
        return sum([item.cost() for item in self._items])
    
    def get_items(self):
        return self._items

    def get_required_ingredients(self) -> list:
        all_ingredients = []
        for item in self._items:
            all_ingredients.extend(item.get_required_ingredients())
        return all_ingredients

# --- FEATURE 2: Chain of Responsibility (Discount & Tax) ---
class PriceHandler(ABC):
    def __init__(self, next_handler=None):
        self.next_handler = next_handler
        
    @abstractmethod
    def handle(self, amount: float, promo_code: str) -> float:
        if self.next_handler:
            return self.next_handler.handle(amount, promo_code)
        return amount

class CouponHandler(PriceHandler):
    def handle(self, amount: float, promo_code: str) -> float:
        if promo_code:
            from .models import DiscountCode
            try:
                discount = DiscountCode.objects.get(code__iexact=promo_code)
                if discount.discount_amount > 0:
                    amount = max(0, amount - float(discount.discount_amount))
                if discount.discount_percent > 0:
                    amount = amount * (1 - (discount.discount_percent / 100.0))
            except DiscountCode.DoesNotExist:
                pass
        
        if self.next_handler:
            return self.next_handler.handle(amount, promo_code)
        return amount

class VatHandler(PriceHandler):
    """Tax Handler - ปัจจุบันร้านใช้ราคา Net (ไม่มีการคิดภาษี VAT 7% เพิ่มเติม)"""
    def handle(self, amount: float, promo_code: str) -> float:
        # ไม่คิดภาษี VAT เพิ่มเติม (ราคาสุทธิ Net Price)
        if self.next_handler:
            return self.next_handler.handle(amount, promo_code)
        return amount

# --- FEATURE 3: Singleton Pattern (Inventory DB Wrapper) ---
class InventoryManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(InventoryManager, cls).__new__(cls)
        return cls._instance
        
    def deduct_stock(self, item_name: str, qty: int = 1) -> bool:
        from .models import InventoryItem
        try:
            # Exact match (case-insensitive) first, then fallback to contains
            item = InventoryItem.objects.filter(name__iexact=item_name).first()
            if not item:
                item = InventoryItem.objects.filter(name__icontains=item_name).first()
                
            if item and item.quantity >= qty:
                item.quantity -= qty
                item.save()
                return True
            return False
        except Exception:
            return False
        
    def get_stock(self):
        from .models import InventoryItem
        return {item.name: item.quantity for item in InventoryItem.objects.all()}

# --- State Pattern (Order State Management) ---
class OrderState(ABC):
    @abstractmethod
    def next_state(self, order): pass
    @abstractmethod
    def cancel(self, order): pass
    @abstractmethod
    def get_status_name(self) -> str: pass
    @abstractmethod
    def get_db_value(self) -> str: pass

class PendingState(OrderState):
    def next_state(self, order): order.set_state(BrewingState())
    def cancel(self, order): order.set_state(CanceledState())
    def get_status_name(self) -> str: return "Pending"
    def get_db_value(self) -> str: return "PENDING"

class BrewingState(OrderState):
    def next_state(self, order): order.set_state(CompletedState())
    def cancel(self, order): raise ValueError("Cannot cancel an order that is already brewing")
    def get_status_name(self) -> str: return "Brewing"
    def get_db_value(self) -> str: return "BREWING"

class CompletedState(OrderState):
    def next_state(self, order): pass
    def cancel(self, order): raise ValueError("Cannot cancel a completed order")
    def get_status_name(self) -> str: return "Completed"
    def get_db_value(self) -> str: return "COMPLETED"

class CanceledState(OrderState):
    def next_state(self, order): pass
    def cancel(self, order): pass
    def get_status_name(self) -> str: return "Canceled"
    def get_db_value(self) -> str: return "CANCELED"

# --- FEATURE 5: Template Method Pattern (Export Report) ---
class SalesReportTemplate(ABC):
    def generate_report(self, orders_data) -> str:
        """This is the Template Method that dictates the skeleton of the algorithm"""
        header = self.format_header()
        body = self.format_body(orders_data)
        footer = self.format_footer(orders_data)
        return header + body + footer
        
    @abstractmethod
    def format_header(self) -> str: pass
    
    @abstractmethod
    def format_body(self, orders_data) -> str: pass
    
    def format_footer(self, orders_data) -> str:
        # Default footer (can be overridden)
        total = sum(order['total_cost'] for order in orders_data)
        return f"\nTotal Revenue: {total} THB\n"

class CsvReportGenerator(SalesReportTemplate):
    def format_header(self) -> str:
        return "ID,Description,Cost,Status\n"
        
    def format_body(self, orders_data) -> str:
        lines = []
        for o in orders_data:
            desc = o['description'].replace(',', '|') # safe csv
            lines.append(f"{o['id']},{desc},{o['total_cost']},{o['status']}")
        return "\n".join(lines)
        
    def format_footer(self, orders_data) -> str:
        total = sum(order['total_cost'] for order in orders_data)
        return f"\n,,,TOTAL: {total}\n"

class TxtReportGenerator(SalesReportTemplate):
    def format_header(self) -> str:
        return "=== DAILY CAFE SALES REPORT ===\n\n"
        
    def format_body(self, orders_data) -> str:
        lines = []
        for o in orders_data:
            lines.append(f"Order #{o['id']} [{o['status']}]: {o['description']} -> {o['total_cost']} THB")
        return "\n".join(lines)

# --- FEATURE 6: Strategy Pattern (Payment Processing) ---
class PaymentStrategy(ABC):
    @abstractmethod
    def pay(self, amount: float) -> dict:
        """Process payment and return result dictionary with receipt info"""
        pass

class CashPayment(PaymentStrategy):
    def __init__(self, amount_tendered: float = None):
        self.amount_tendered = float(amount_tendered) if amount_tendered is not None else None
        
    def pay(self, amount: float) -> dict:
        amount = round(amount, 2)
        tendered = self.amount_tendered if self.amount_tendered is not None else amount
        if tendered < amount:
            shortage = round(amount - tendered, 2)
            raise ValueError(f"ยอดเงินสดไม่เพียงพอ (ยอดที่ต้องชำระ {amount} ฿, รับเงินมา {tendered} ฿, ขาดอีก {shortage} ฿)")
        
        change = round(tendered - amount, 2)
        return {
            'payment_method': 'CASH',
            'method_name': 'เงินสด (Cash)',
            'amount_paid': tendered,
            'change': change,
            'reference': f"CASH-{int(tendered)}"
        }

class PromptPayPayment(PaymentStrategy):
    def __init__(self, reference: str = ""):
        self.reference = reference
        
    def pay(self, amount: float) -> dict:
        import uuid
        amount = round(amount, 2)
        ref = self.reference or f"PP-{uuid.uuid4().hex[:8].upper()}"
        return {
            'payment_method': 'PROMPTPAY',
            'method_name': 'พร้อมเพย์ QR (PromptPay)',
            'amount_paid': amount,
            'change': 0.0,
            'reference': ref
        }

# --- Facade Pattern (Checkout Process Orchestrator) ---
class CheckoutFacade:
    def __init__(self):
        self.inventory = InventoryManager()
        # Chain setup: Coupon -> VAT
        self.pricing_chain = CouponHandler(VatHandler())
        
    def place_order(self, cart: OrderCart, promo_code: str = "", payment_strategy: PaymentStrategy = None):
        if not cart.get_items():
            raise ValueError("Cart is empty")

        base_amount = cart.cost()
        final_amount = self.pricing_chain.handle(base_amount, promo_code)
        final_amount = round(final_amount, 2)
        
        # 1. Process payment via Strategy Pattern
        if payment_strategy is None:
            payment_strategy = CashPayment(amount_tendered=final_amount)
            
        payment_info = payment_strategy.pay(final_amount)
        
        # 2. Deduct Inventory based on Recipe Model & Decorators (No naive string matching!)
        required_ingredients = cart.get_required_ingredients()
        for ing_name, ing_qty in required_ingredients:
            self.inventory.deduct_stock(ing_name, ing_qty)
        
        return {
            'description': cart.get_description(),
            'total_cost': final_amount,
            'initial_status': PendingState().get_db_value(),
            'payment_info': payment_info
        }
