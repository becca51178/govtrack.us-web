from models import Req
from django.core.cache import cache
from django.conf import settings
 
import urllib, json, datetime

from emailverification.models import BouncedEmail

if settings.GEOIP_DB_PATH:
	from django.contrib.gis.geoip import GeoIP
	geo_ip_db = GeoIP(settings.GEOIP_DB_PATH)
	washington_dc = geo_ip_db.geos("69.255.139.56")

# http://whois.arin.net/rest/org/ISUHR/nets
HOUSE_NET_RANGES = (
    ("143.231.0.0", "143.231.255.255"),
    ("137.18.0.0", "137.18.255.255"),
    ("143.228.0.0", "143.228.255.255"),
    ("12.185.56.0", "12.185.56.7"),
    ("12.147.170.144", "12.147.170.159"),
    ("74.119.128.0", "74.119.131.255"),
    )
# http://whois.arin.net/rest/org/USSAA/nets
SENATE_NET_RANGES = (
    ("156.33.0.0", "156.33.255.255"),
    )

def template_context_processor(request):
	# These are good to have in a context processor and not middleware
	# because they won't be evaluated until template evaluation, which
	# might have user-info blocked already for caching (a good thing).
	
    context = {
    	"GOOGLE_ANALYTICS_KEY": settings.GOOGLE_ANALYTICS_KEY
    }
    
    if request.user.is_authenticated() and BouncedEmail.objects.filter(user=request.user).exists(): context["user_has_bounced_mail"] = True
    
    # Add context variables for whether the user is in the
    # House or Senate netblocks.
    
    def ip_to_quad(ip):
        return [int(s) for s in ip.split(".")]
    def compare_ips(ip1, ip2):
        return cmp(ip_to_quad(ip1), ip_to_quad(ip2))
    def is_ip_in_range(ip, block):
       return compare_ips(ip, block[0]) >= 0 and compare_ips(ip, block[1]) <= 0
    def is_ip_in_any_range(ip, blocks):
       for block in blocks:
           if is_ip_in_range(ip, block):
               return True
       return False
    
    try:
        ip = request.META["REMOTE_ADDR"]
        ip = ip.replace("::ffff:", "") # ipv6 wrapping ipv4
    	
        if is_ip_in_any_range(ip, HOUSE_NET_RANGES):
            context["remote_net_house"] = True
        if is_ip_in_any_range(ip, SENATE_NET_RANGES):
            context["remote_net_senate"] = True
            
        if settings.GEOIP_DB_PATH:
            context["is_dc_local"] = geo_ip_db.geos(ip).distance(washington_dc) < .5
    except:
        pass
    
    return context
    
class DebugMiddleware:
    def process_request(self, request):
        r = Req(request=repr(request))
        r.save()
        request._debug_req = r
        return None
    def process_response(self, request, response):
        if getattr(request, "_debug_req", None) != None:
            request._debug_req.delete()
            request._debug_req = None
        return response
    def process_exception(self, request, exception):
        if getattr(request, "_debug_req", None) != None:
            request._debug_req.delete()
            request._debug_req = None
        return None
        
