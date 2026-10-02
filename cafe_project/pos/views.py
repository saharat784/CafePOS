from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse
from .models import Order, Category, MenuItem
from .services import (
    ConcreteProduct, Milk, Syrup, TemperatureDecorator, SweetnessDecorator,
    CashPayment, PromptPayPayment,
    CheckoutFacade, OrderCart, InventoryManager,
    CsvReportGenerator, TxtReportGenerator
)

def index(request):
    """Redirect to menu"""
    return redirect('menu')

def menu(request):
    """Menu Page displaying items in a grid"""
    categories = Category.objects.prefetch_related('menuitem_set').all()
    
    if request.method == 'POST':
        item_id = request.POST.get('item_id')
        item = MenuItem.objects.get(id=item_id)
        qty = max(1, int(request.POST.get('quantity', 1)))
        temperature = request.POST.get('temperature', '').strip()
        sweetness = request.POST.get('sweetness', '').strip()
        milk = request.POST.get('milk') == 'true'
        syrup = request.POST.get('syrup') == 'true'
        
        if 'cart' not in request.session:
            request.session['cart'] = []
            
        # Check if identical item already in cart
        found = False
        for cart_item in request.session['cart']:
            if (cart_item['id'] == item.id and 
                cart_item.get('temperature', '') == temperature and
                cart_item.get('sweetness', '') == sweetness and
                cart_item.get('milk') == milk and 
                cart_item.get('syrup') == syrup):
                cart_item['quantity'] = cart_item.get('quantity', 1) + qty
                found = True
                break
                
        if not found:
            request.session['cart'].append({
                'id': item.id,
                'name': item.name,
                'price': float(item.price),
                'is_drink': item.is_drink,
                'temperature': temperature,
                'sweetness': sweetness,
                'milk': milk,
                'syrup': syrup,
                'quantity': qty,
            })
            
        request.session.modified = True
        messages.success(request, f"เพิ่ม {item.name} ({qty} รายการ) ลงในตะกร้าแล้ว")
        return redirect('menu')
        
    cart_count = sum(item.get('quantity', 1) for item in request.session.get('cart', []))
    return render(request, 'pos/menu.html', {'categories': categories, 'cart_count': cart_count})

def cart(request):
    """Cart Page handling checkout"""
    cart_data = request.session.get('cart', [])
    
    if request.method == 'POST':
        if 'checkout' in request.POST:
            if not cart_data:
                messages.error(request, "Cart is empty!")
                return redirect('cart')

            order_cart = OrderCart()
            for item in cart_data:
                qty = int(item.get('quantity', 1))
                for _ in range(qty):
                    menu_item = MenuItem.objects.get(id=item['id'])
                    beverage = ConcreteProduct(menu_item)
                    
                    # Apply decorators
                    if item.get('temperature'):
                        beverage = TemperatureDecorator(beverage, item['temperature'])
                    if item.get('sweetness'):
                        beverage = SweetnessDecorator(beverage, item['sweetness'])
                    if item.get('milk'): 
                        beverage = Milk(beverage)
                    if item.get('syrup'): 
                        beverage = Syrup(beverage)
                    
                    order_cart.add_item(beverage)

            promo_code = request.POST.get('promo_code', '').strip()
            payment_type = request.POST.get('payment_method', 'cash')
            
            # Select Payment Strategy (Strategy Pattern)
            try:
                if payment_type == 'promptpay':
                    payment_strategy = PromptPayPayment()
                else:
                    cash_input = request.POST.get('cash_amount', '').strip()
                    amount_tendered = float(cash_input) if cash_input else None
                    payment_strategy = CashPayment(amount_tendered=amount_tendered)

                facade = CheckoutFacade()
                order_data = facade.place_order(order_cart, promo_code, payment_strategy=payment_strategy)
                pay_info = order_data['payment_info']

                order = Order.objects.create(
                    description=order_data['description'],
                    total_cost=order_data['total_cost'],
                    status=order_data['initial_status'],
                    payment_method=pay_info['payment_method'],
                    amount_paid=pay_info['amount_paid'],
                    change_amount=pay_info['change'],
                    payment_ref=pay_info['reference']
                )
                request.session['cart'] = []
                
                if pay_info['payment_method'] == 'CASH':
                    messages.success(request, f"สั่งซื้อสำเร็จ! คิว #{order.id} | ชำระเงินสด {order.total_cost} ฿ (รับเงิน {order.amount_paid} ฿, เงินทอน {order.change_amount} ฿)")
                else:
                    messages.success(request, f"สั่งซื้อสำเร็จ! คิว #{order.id} | ชำระผ่านพร้อมเพย์ {order.total_cost} ฿ (Ref: {order.payment_ref})")
                    
                return redirect('customer_queue')
            except ValueError as e:
                messages.error(request, str(e))
                return redirect('cart')
                
        elif 'change_qty' in request.POST:
            index = int(request.POST.get('item_index'))
            qty_action = request.POST.get('qty_action')
            if 0 <= index < len(request.session['cart']):
                current_qty = request.session['cart'][index].get('quantity', 1)
                if qty_action == 'increase':
                    request.session['cart'][index]['quantity'] = current_qty + 1
                elif qty_action == 'decrease':
                    if current_qty > 1:
                        request.session['cart'][index]['quantity'] = current_qty - 1
                    else:
                        request.session['cart'].pop(index)
                request.session.modified = True
            return redirect('cart')

        elif 'remove_item' in request.POST:
            index = int(request.POST.get('item_index'))
            if 0 <= index < len(request.session['cart']):
                removed_item = request.session['cart'].pop(index)
                request.session.modified = True
                messages.success(request, f"Removed {removed_item['name']} from cart.")
            return redirect('cart')

        elif 'clear_cart' in request.POST:
            request.session['cart'] = []
            return redirect('cart')

    enriched_cart = []
    cart_subtotal = 0.0
    item_ids = [item['id'] for item in cart_data if 'id' in item]
    menu_map = {m.id: m for m in MenuItem.objects.filter(id__in=item_ids)} if item_ids else {}
    for idx, item in enumerate(cart_data):
        qty = int(item.get('quantity', 1))
        unit_price = float(item['price'])
        if item.get('milk'): unit_price += 15.0
        if item.get('syrup'): unit_price += 10.0
        row_total = unit_price * qty
        cart_subtotal += row_total
        menu_obj = menu_map.get(item.get('id'))
        img_url = menu_obj.get_image if menu_obj else ''
        enriched_cart.append({
            **item,
            'index': idx,
            'image_url': img_url,
            'quantity': qty,
            'unit_price': unit_price,
            'total_price': row_total
        })

    cart_count = sum(item.get('quantity', 1) for item in cart_data)
    return render(request, 'pos/cart.html', {
        'cart_items': enriched_cart, 
        'cart_subtotal': cart_subtotal,
        'cart_count': cart_count
    })

from django.utils.timezone import now

def barista(request):
    """Barista dashboard (KDS) with Kanban view"""
    if request.method == 'POST':
        order_id = request.POST.get('order_id')
        order = Order.objects.get(id=order_id)
        
        if 'cancel' in request.POST:
            try:
                order.cancel()
                messages.success(request, f"Order #{order.id} was voided.")
            except ValueError as e:
                messages.error(request, str(e))
        else:
            order.proceed()
            
        return redirect('barista')
        
    orders = Order.objects.exclude(status='CANCELED').order_by('created_at')
    
    current_time = now()
    pending_orders = []
    brewing_orders = []
    completed_orders = []
    
    for o in orders:
        o.wait_mins = int((current_time - o.created_at).total_seconds() / 60.0)
        if o.status == 'PENDING':
            pending_orders.append(o)
        elif o.status == 'BREWING':
            brewing_orders.append(o)
        elif o.status == 'COMPLETED':
            completed_orders.append(o)
            
    # Keep only recent 10 completed orders to avoid clutter
    completed_orders = completed_orders[-10:]

    return render(request, 'pos/barista.html', {
        'pending_orders': pending_orders,
        'brewing_orders': brewing_orders,
        'completed_orders': completed_orders[::-1] # Reverse to show newest first
    })

def inventory(request):
    """Inventory Manager Dashboard"""
    inv = InventoryManager()
    return render(request, 'pos/inventory.html', {'stock': inv.get_stock()})

def export_report(request):
    """Export daily sales using Template Method Pattern"""
    format_type = request.GET.get('format', 'txt')
    
    # Prepare data dictionary for the report generators
    orders = Order.objects.filter(status='COMPLETED')
    orders_data = [
        {'id': o.id, 'description': o.description, 'total_cost': o.total_cost, 'status': o.status}
        for o in orders
    ]
    
    if format_type == 'csv':
        generator = CsvReportGenerator()
        content = generator.generate_report(orders_data)
        response = HttpResponse(content, content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="sales_report.csv"'
    else:
        generator = TxtReportGenerator()
        content = generator.generate_report(orders_data)
        response = HttpResponse(content, content_type='text/plain')
        response['Content-Disposition'] = 'attachment; filename="sales_report.txt"'
        
    return response

from .models import InventoryItem, DiscountCode
def custom_admin(request):
    """Custom Manager Dashboard for CRUD"""
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add_menu':
            cat_id = request.POST.get('category')
            MenuItem.objects.create(
                name=request.POST.get('name'),
                category_id=cat_id,
                price=request.POST.get('price'),
                image_url=request.POST.get('image_url') or 'https://images.unsplash.com/photo-1541167760496-1628856ab772?w=300&h=300&fit=crop',
                image=request.FILES.get('image'),
                is_drink=request.POST.get('is_drink') == 'on'
            )
            messages.success(request, "Menu item added!")
            
        elif action == 'edit_menu':
            item = MenuItem.objects.get(id=request.POST.get('item_id'))
            item.name = request.POST.get('name')
            item.category_id = request.POST.get('category')
            item.price = request.POST.get('price')
            if request.FILES.get('image'):
                item.image = request.FILES.get('image')
            item.is_drink = request.POST.get('is_drink') == 'on'
            item.save()
            messages.success(request, f"Menu item '{item.name}' updated!")
            
        elif action == 'delete_menu':
            MenuItem.objects.filter(id=request.POST.get('item_id')).delete()
            messages.success(request, "Menu item deleted!")
            
        elif action == 'add_inventory':
            InventoryItem.objects.create(
                name=request.POST.get('name'),
                quantity=request.POST.get('quantity')
            )
            messages.success(request, "Inventory item added!")
            
        elif action == 'update_inventory':
            item = InventoryItem.objects.get(id=request.POST.get('item_id'))
            item.quantity = request.POST.get('quantity')
            item.save()
            messages.success(request, "Inventory updated!")
            
        elif action == 'add_discount':
            DiscountCode.objects.create(
                code=request.POST.get('code'),
                discount_amount=request.POST.get('discount_amount') or 0,
                discount_percent=request.POST.get('discount_percent') or 0
            )
            messages.success(request, "Discount code created!")
            
        elif action == 'delete_discount':
            DiscountCode.objects.filter(id=request.POST.get('code_id')).delete()
            messages.success(request, "Discount code deleted!")
            
        elif action == 'add_recipe':
            menu_id = request.POST.get('menu_id')
            ing_id = request.POST.get('ingredient_id')
            qty_req = int(request.POST.get('quantity_required', 1))
            from .models import RecipeItem
            RecipeItem.objects.create(
                menu_item_id=menu_id,
                ingredient_id=ing_id,
                quantity_required=qty_req
            )
            messages.success(request, "สูตรเมนูถูกผูกเข้ากับวัตถุดิบเรียบร้อยแล้ว!")
            
        elif action == 'delete_recipe':
            from .models import RecipeItem
            RecipeItem.objects.filter(id=request.POST.get('recipe_id')).delete()
            messages.success(request, "ลบสูตรวัตถุดิบเรียบร้อยแล้ว!")
            
        return redirect('custom_admin')

    from .models import RecipeItem
    context = {
        'menu_items': MenuItem.objects.prefetch_related('recipe_items__ingredient').all(),
        'categories': Category.objects.all(),
        'inventory_items': InventoryItem.objects.all(),
        'discount_codes': DiscountCode.objects.all(),
        'recipe_items': RecipeItem.objects.select_related('menu_item', 'ingredient').all(),
    }
    return render(request, 'pos/custom_admin.html', context)

from django.http import JsonResponse

def customer_queue(request):
    """Customer-facing live queue display board"""
    preparing_orders = Order.objects.filter(status__in=['PENDING', 'BREWING']).order_by('created_at')
    ready_orders = Order.objects.filter(status='COMPLETED').order_by('-created_at')[:12]
    
    return render(request, 'pos/customer_queue.html', {
        'preparing_orders': preparing_orders,
        'ready_orders': ready_orders
    })

def api_orders(request):
    """JSON API for real-time customer queue polling"""
    pending = list(Order.objects.filter(status='PENDING').order_by('created_at').values('id', 'status', 'description'))
    brewing = list(Order.objects.filter(status='BREWING').order_by('created_at').values('id', 'status', 'description'))
    completed = list(Order.objects.filter(status='COMPLETED').order_by('-created_at')[:12].values('id', 'status', 'description'))
    
    return JsonResponse({
        'pending': pending,
        'brewing': brewing,
        'completed': completed
    })


