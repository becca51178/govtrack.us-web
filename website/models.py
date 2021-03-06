from django.db import models

from django.contrib.auth.models import User

from events.models import Feed, SubscriptionList

class UserProfile(models.Model):
    user = models.ForeignKey(User, unique=True, db_index=True)
    massemail = models.BooleanField(default=True) # may we send you mail?
    old_id = models.IntegerField(blank=True, null=True) # from the pre-2012 GovTrack database
    
    def lists(self):
        # make sure the 'default' list exists
        SubscriptionList.objects.get_or_create(
            user = self.user,
            is_default = True,
            defaults = { "name": "Email Updates" , "email": 1 } )
        return SubscriptionList.objects.filter(user=self.user).order_by('name')
    def lists_with_email(self):
        # return lists with trackers with email updates turned on
        return SubscriptionList.objects.filter(user=self.user, email__gt=0, trackers__id__gt=0).distinct().order_by('name')
    
def get_user_profile(user):
    if hasattr(user, "_profile"): return user._profile
    profile, isnew = UserProfile.objects.get_or_create(user = user)
    user._profile = profile
    return profile
User.userprofile = get_user_profile 
    
class CampaignSupporter(models.Model):
    campaign = models.CharField(max_length=96)
    prefix = models.CharField(max_length=96)
    firstname = models.CharField(max_length=96)
    lastname = models.CharField(max_length=96)
    address = models.CharField(max_length=96)
    city = models.CharField(max_length=96)
    state = models.CharField(max_length=96)
    zipcode = models.CharField(max_length=96)
    email = models.CharField(max_length=96)
    message = models.CharField(max_length=256, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    district = models.IntegerField(blank=True, null=True)
    geocode_response = models.TextField(blank=True, null=True)
   
class Req(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    request = models.TextField()

from bill.models import Bill
class CommunityInterest(models.Model):
    user = models.ForeignKey(User)
    bill = models.ForeignKey(Bill)
    methods = models.CharField(max_length=32)
    created = models.DateTimeField(auto_now_add=True)
    class Meta:
        unique_together = ( ('user', 'bill'), )

