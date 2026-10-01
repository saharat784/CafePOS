from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse
from .models import Order, Category, MenuItem
from .services import (
    ConcreteProduct, Milk, Syrup, CheckoutFacade, OrderCart, InventoryManager,
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
        
        cart_item = {
            'id': item.id,
            'name': item.name,
            'price': float(item.price),
            'is_drink': item.is_drink,
            'milk': request.POST.get('milk') == 'true',
            'syrup': request.POST.get('syrup') == 'true',
        }
        
        if 'cart' not in request.session:
            request.session['cart'] = []
            
        request.session['cart'].append(cart_item)
        request.session.modified = True
        messages.success(request, f"Added {item.name} to cart.")
        return redirect('menu')
        
    cart_count = len(request.session.get('cart', []))
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
                menu_item = MenuItem.objects.get(id=item['id'])
                beverage = ConcreteProduct(menu_item)
                
                # Apply decorators if drink
                if item.get('milk'): beverage = Milk(beverage)
                if item.get('syrup'): beverage = Syrup(beverage)
                
                order_cart.add_item(beverage)

            promo_code = request.POST.get('promo_code', '')
            
            facade = CheckoutFacade()
            try:
                order_data = facade.place_order(order_cart, promo_code)
                Order.objects.create(
                    description=order_data['description'],
                    total_cost=order_data['total_cost'],
                    status=order_data['initial_status']
                )
                request.session['cart'] = [] 
                messages.success(request, f"Order placed successfully! Total: {order_data['total_cost']} THB")
                return redirect('menu')
            except ValueError as e:
                messages.error(request, str(e))
                
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

    return render(request, 'pos/cart.html', {'cart_items': cart_data})

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
            
        return redirect('custom_admin')

    context = {
        'menu_items': MenuItem.objects.all(),
        'categories': Category.objects.all(),
        'inventory_items': InventoryItem.objects.all(),
        'discount_codes': DiscountCode.objects.all(),
    }
    return render(request, 'pos/custom_admin.html', context)

