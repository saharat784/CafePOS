from django.db import models
from .services import PendingState, BrewingState, CompletedState, CanceledState

class Category(models.Model):
    name = models.CharField(max_length=100)
    def __str__(self): return self.name

class MenuItem(models.Model):
    name = models.CharField(max_length=100)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    image_url = models.URLField(max_length=500, blank=True, default="https://images.unsplash.com/photo-1541167760496-1628856ab772?w=300&h=300&fit=crop")
    image = models.ImageField(upload_to='menu_images/', blank=True, null=True)
    is_drink = models.BooleanField(default=True)
    
    def __str__(self): return f"{self.name} ({self.price} THB)"
    
    @property
    def get_image(self):
        if self.image:
            return self.image.url
        return self.image_url

class InventoryItem(models.Model):
    name = models.CharField(max_length=100, unique=True)
    quantity = models.IntegerField(default=0)
    
    def __str__(self): return f"{self.name}: {self.quantity}"

class DiscountCode(models.Model):
    code = models.CharField(max_length=20, unique=True)
    discount_amount = models.DecimalField(max_digits=6, decimal_places=2, default=0) # Flat amount
    discount_percent = models.IntegerField(default=0) # e.g. 50 for 50%
    
    def __str__(self): return self.code

class Order(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending (รอคิวชง)'),
        ('BREWING', 'Brewing (กำลังชง)'),
        ('COMPLETED', 'Completed (เสร็จสิ้น)'),
        ('CANCELED', 'Canceled (ยกเลิก)'),
    ]
    
    description = models.TextField()
    total_cost = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order #{self.id} - {self.description} ({self.get_status_display()})"

    def _get_state_object(self):
        if self.status == 'PENDING': return PendingState()
        elif self.status == 'BREWING': return BrewingState()
        elif self.status == 'CANCELED': return CanceledState()
        else: return CompletedState()

    def set_state(self, state_obj):
        self.status = state_obj.get_db_value()

    def proceed(self):
        current_state_obj = self._get_state_object()
        current_state_obj.next_state(self)
        self.save()
        
    def cancel(self):
        current_state_obj = self._get_state_object()
        current_state_obj.cancel(self)
        self.save()

