from django.contrib import admin
from .models import Category, MenuItem, InventoryItem, DiscountCode, Order

admin.site.register(Category)
admin.site.register(MenuItem)
admin.site.register(InventoryItem)
admin.site.register(DiscountCode)
admin.site.register(Order)
