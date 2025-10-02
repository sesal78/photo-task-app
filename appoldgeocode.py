import streamlit as st
import json
import os
import random
import requests
from datetime import datetime

# -------------------------------
# Storage (local JSON)
# -------------------------------
HISTORY_FILE = "task_history.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            try:
                return json.load(f)
            except:
                return []
    return []

def save_task(task):
    history = load_history()
    history.append(task)
    history = history[-7:]  # keep last 7
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)
    return history

# -------------------------------
# Location Intelligence APIs (Google → OSM fallback)
# -------------------------------
@st.cache_data(ttl=86400)
def geocode_location(query):
    """Geocode location using Google Maps → fallback to OpenStreetMap"""
    # Try Google Maps Geocoding API first
    try:
        if "GOOGLE_MAPS_KEY" in st.secrets:
            url = "https://maps.googleapis.com/maps/api/geocode/json"
            params = {"address": query, "key": st.secrets["GOOGLE_MAPS_KEY"]}
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            if data.get("status") == "OK":
                loc = data["results"][0]["geometry"]["location"]
                return {
                    "lat": loc["lat"],
                    "lon": loc["lng"],
                    "display_name": data["results"][0]["formatted_address"],
                    "source": "Google Maps"
                }
    except Exception as e:
        st.warning(f"⚠️ Google Geocoding failed, using OpenStreetMap fallback: {e}")

    # Fallback to OpenStreetMap Nominatim
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": query, "format": "json", "limit": 1}
        r = requests.get(url, params=params, headers={"User-Agent": "PhotoTaskApp/1.0"}, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data:
            return {
                "lat": float(data[0]["lat"]),
                "lon": float(data[0]["lon"]),
                "display_name": data[0]["display_name"],
                "source": "OpenStreetMap"
            }
    except Exception as e:
        st.warning(f"⚠️ Geocoding failed completely: {e}")
    
    return None

@st.cache_data(ttl=3600)
def fetch_pois_overpass(lat, lon, radius_m=800):
    """Fetch nearby points of interest using Overpass API (OSM fallback)"""
    try:
        query = f"""
        [out:json][timeout:25];
        (
          node(around:{radius_m},{lat},{lon})["tourism"~"attraction|viewpoint|museum|artwork"];
          node(around:{radius_m},{lat},{lon})["amenity"~"marketplace|cafe|bar|restaurant|place_of_worship|theatre|library"];
          node(around:{radius_m},{lat},{lon})["leisure"~"park|garden|marina"];
          node(around:{radius_m},{lat},{lon})["shop"~"mall|department_store|supermarket"];
          node(around:{radius_m},{lat},{lon})["natural"~"beach|cliff|coastline|wetland"];
          node(around:{radius_m},{lat},{lon})["man_made"~"bridge|pier|lighthouse"];
          way(around:{radius_m},{lat},{lon})["tourism"~"attraction|viewpoint|museum|artwork"];
          way(around:{radius_m},{lat},{lon})["leisure"~"park|garden|marina"];
          way(around:{radius_m},{lat},{lon})["natural"~"beach|cliff|coastline|wetland"];
          way(around:{radius_m},{lat},{lon})["man_made"~"bridge|pier|lighthouse"];
        );
        out center 60;
        """
        r = requests.post("https://overpass-api.de/api/interpreter", data=query, 
                         headers={"User-Agent": "PhotoTaskApp/1.0"}, timeout=30)
        r.raise_for_status()
        data = r.json().get("elements", [])
        pois = []
        for e in data:
            tags = e.get("tags", {})
            name = tags.get("name") or tags.get("ref") or ""
            lat_e = e.get("lat") or (e.get("center") or {}).get("lat")
            lon_e = e.get("lon") or (e.get("center") or {}).get("lon")
            if lat_e and lon_e:
                pois.append({
                    "id": f"{e.get('type','n')}/{e.get('id')}",
                    "name": name,
                    "lat": lat_e,
                    "lon": lon_e,
                    "tags": tags
                })
        # Prefer named POIs
        pois.sort(key=lambda p: (0 if p["name"] else 1, p["id"]))
        return pois[:40]
    except Exception as e:
        st.warning(f"⚠️ Overpass API failed: {e}")
        return []

@st.cache_data(ttl=3600)
def fetch_pois(lat, lon, radius_m=800):
    """Fetch nearby POIs using Google Places → fallback to Overpass"""
    # Try Google Places API first
    try:
        if "GOOGLE_MAPS_KEY" in st.secrets:
            url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
            params = {
                "location": f"{lat},{lon}",
                "radius": radius_m,
                "key": st.secrets["GOOGLE_MAPS_KEY"]
            }
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            if data.get("status") == "OK":
                pois = []
                for place in data["results"][:40]:
                    pois.append({
                        "id": place["place_id"],
                        "name": place.get("name", ""),
                        "lat": place["geometry"]["location"]["lat"],
                        "lon": place["geometry"]["location"]["lng"],
                        "tags": {"type": "google_place", "types": place.get("types", [])},
                        "source": "Google Places"
                    })
                return pois
    except Exception as e:
        st.warning(f"⚠️ Google Places failed, using Overpass fallback: {e}")

    # Fallback to Overpass (OSM)
    return fetch_pois_overpass(lat, lon, radius_m)

@st.cache_data(ttl=3600)
def get_sun_times(lat, lon, date_str=None):
    """Get sunrise/sunset times"""
    try:
        params = {"lat": lat, "lng": lon, "formatted": 0}
        if date_str:
            params["date"] = date_str
        r = requests.get("https://api.sunrise-sunset.org/json", params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("results", {})
    except Exception as e:
        return {}

@st.cache_data(ttl=900)
def get_weather_open_meteo(lat, lon):
    """Get current weather using Open-Meteo (free, no key) - fallback"""
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat, "longitude": lon,
            "current_weather": True,
            "hourly": "cloudcover,precipitation,visibility"
        }
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {}

@st.cache_data(ttl=900)
def get_weather(lat, lon):
    """Fetch current weather via OpenWeather → fallback to Open-Meteo"""
    # Try OpenWeatherMap first
    try:
        if "OPENWEATHER_KEY" in st.secrets:
            url = "https://api.openweathermap.org/data/2.5/weather"
            params = {
                "lat": lat, 
                "lon": lon, 
                "appid": st.secrets["OPENWEATHER_KEY"], 
                "units": "metric"
            }
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            main = data.get("main", {})
            wind = data.get("wind", {})
            weather_desc = data.get("weather", [{}])[0].get("description", "")
            return f"{main.get('temp','?')}°C | {weather_desc} | {main.get('humidity','?')}% humidity | wind {wind.get('speed','?')}m/s"
    except Exception as e:
        st.warning(f"⚠️ OpenWeather failed, using Open-Meteo fallback: {e}")

    # Fallback to Open-Meteo
    fallback = get_weather_open_meteo(lat, lon)
    if fallback.get("current_weather"):
        w = fallback["current_weather"]
        return f"{w.get('temperature','?')}°C | wind {w.get('windspeed','?')}km/h"
    return ""

# -------------------------------
# Enhanced Photo Task Planner Core
# -------------------------------
class PhotoTaskPlanner:
    def __init__(self):
        # 🎯 Pre-built location dictionaries (AU + examples)
        self.city_guides = {
            "melbourne cbd": {
                "genres": ["street", "cityscape", "architecture"],
                "suggested_spots": [
                    "Flinders Street Station for architecture + people flow",
                    "Hosier Lane for graffiti/texture abstracts",
                    "Trams on Bourke Street for motion blur",
                    "Southbank for skyline + river reflections",
                    "Federation Square for geometric patterns"
                ],
                "specific_steps": [
                    "Shoot motion blur of tram passing at 1/15s shutter",
                    "Capture layered crossing at Flinders with pedestrians + skyline",
                    "Frame graffiti walls in Hosier Lane with passerby for scale",
                    "Look for golden hour reflections on glass facades along Collins St",
                    "Photograph commuter flow at Southern Cross Station"
                ]
            },
            "geelong": {
                "genres": ["cityscape", "urban nature", "abstract"],
                "suggested_spots": [
                    "Geelong Waterfront bollards",
                    "Eastern Beach boardwalk",
                    "Cunningham Pier for symmetry",
                    "Botanic Gardens for textures/close-ups",
                    "Steampacket Gardens for waterfront views"
                ],
                "specific_steps": [
                    "Shoot bollard figures as foreground with bay in background",
                    "Capture long pier symmetry with leading lines",
                    "Use reflections from water surface for abstract frames",
                    "Focus on details: textures of old boats, rust, wood patterns",
                    "Photograph sunset silhouettes along the foreshore"
                ]
            },
            "cairns": {
                "genres": ["nature", "urban nature", "street", "beach"],
                "suggested_spots": [
                    "Esplanade Lagoon for reflections",
                    "Cairns Boardwalk for waterfront shots",
                    "Night Markets for street/documentary",
                    "Muddy's Playground for candid family moments",
                    "Marina for boat details and golden hour"
                ],
                "specific_steps": [
                    "Capture reflections in the lagoon at blue hour",
                    "Photograph palm tree silhouettes against sunset",
                    "Shoot candid moments at the night markets with available light",
                    "Use telephoto to compress boats against mountains",
                    "Look for tropical textures and vibrant colors"
                ]
            },
            "sydney": {
                "genres": ["cityscape", "architecture", "street", "waterfront"],
                "suggested_spots": [
                    "Sydney Opera House for iconic architecture",
                    "Circular Quay for street + waterfront",
                    "The Rocks for historic textures",
                    "Harbour Bridge for leading lines",
                    "Darling Harbour for reflections"
                ],
                "specific_steps": [
                    "Shoot Opera House from Mrs Macquarie's Chair at golden hour",
                    "Capture commuter flow at Circular Quay with ferries in background",
                    "Photograph cobblestone textures and historic facades in The Rocks",
                    "Use Harbour Bridge as leading line with pedestrians for scale",
                    "Look for reflections in Darling Harbour at blue hour"
                ]
            },
            "brisbane": {
                "genres": ["cityscape", "urban nature", "street"],
                "suggested_spots": [
                    "South Bank Parklands",
                    "Story Bridge for cityscape",
                    "Queen Street Mall for street photography",
                    "Brisbane River for reflections",
                    "Kangaroo Point Cliffs for skyline views"
                ],
                "specific_steps": [
                    "Capture Story Bridge lit up at blue hour",
                    "Photograph street performers and crowds at South Bank",
                    "Use river reflections for abstract cityscape compositions",
                    "Shoot skyline from Kangaroo Point with telephoto compression",
                    "Look for leading lines along the riverwalk"
                ]
            },
            "adelaide": {
                "genres": ["cityscape", "beach", "street", "architecture"],
                "suggested_spots": [
                    "Rundle Mall for shopping street flow",
                    "Adelaide Central Market for vibrant colors",
                    "Glenelg Beach jetty for sunset silhouettes",
                    "Adelaide Oval + River Torrens for architecture/water reflections"
                ],
                "specific_steps": [
                    "Photograph street performers or shoppers in Rundle Mall",
                    "Capture stall vendors mid-interaction inside Central Market",
                    "Silhouette subjects walking on Glenelg jetty against sunset",
                    "Shoot Adelaide Oval from the footbridge with skyline background"
                ]
            },
            "perth": {
                "genres": ["beach", "cityscape", "nature"],
                "suggested_spots": [
                    "Cottesloe Beach for golden hour surfers",
                    "Elizabeth Quay for modern architecture",
                    "Kings Park for skyline views with nature foreground"
                ],
                "specific_steps": [
                    "Capture surfers or beachgoers at Cottesloe just before sunset",
                    "Shoot abstracts of public art at Elizabeth Quay",
                    "Frame Perth skyline against foreground trees from Kings Park"
                ]
            },
            "hobart": {
                "genres": ["harbour", "mountains", "architecture"],
                "suggested_spots": [
                    "Salamanca Market for candid vendor/visitor shots",
                    "Mount Wellington for sweeping landscapes",
                    "Constitution Dock for boats and reflections"
                ],
                "specific_steps": [
                    "Capture stall textures + candid haggling at Salamanca Market",
                    "Shoot panoramic landscapes from Mt Wellington at golden hour",
                    "Photograph dockside boats + water reflections"
                ]
            },
            "darwin": {
                "genres": ["wildlife", "beach", "sunset"],
                "suggested_spots": [
                    "Mindil Beach sunset market",
                    "Darwin Botanic Gardens",
                    "Crocosaurus Cove for wildlife"
                ],
                "specific_steps": [
                    "Photograph silhouetted crowds at Mindil Beach markets at sunset",
                    "Focus on tropical textures in Botanic Gardens (palms, flowers)",
                    "Shoot dramatic crocodile detail shots at Crocosaurus Cove"
                ]
            },
            "gold coast": {
                "genres": ["surf", "beach", "cityscape"],
                "suggested_spots": [
                    "Surfers Paradise beach",
                    "SkyPoint Observation Deck",
                    "Broadbeach walkways"
                ],
                "specific_steps": [
                    "Shoot surfers with tele lens, compressing waves",
                    "Capture aerial skyline views from SkyPoint",
                    "Use Broadbeach path lamps as leading lines at dusk"
                ]
            },
            "taronga zoo": {
                "genres": ["wildlife", "portrait", "urban nature"],
                "suggested_spots": [
                    "Elephant trail",
                    "Giraffe outlook (with Sydney skyline in background)",
                    "Seal show area"
                ],
                "specific_steps": [
                    "Photograph giraffes with Opera House/Harbour Bridge background",
                    "Capture sequences of seals in mid-air during show",
                    "Portraits of elephants with tele lens for texture/mood"
                ]
            },
            "taronga western plains": {
                "genres": ["wildlife", "landscape"],
                "suggested_spots": [
                    "Savannah plains exhibit",
                    "Rhino enclosure",
                    "Lion pride lands"
                ],
                "specific_steps": [
                    "Emphasize scale by shooting wide landscapes with giraffes",
                    "Isolate rhino textures with telephoto compression",
                    "Capture lion family interactions with layered framing"
                ]
            },
            "bondi beach": {
                "genres": ["beach", "surf", "street"],
                "suggested_spots": [
                    "Bondi to Bronte coastal walk",
                    "Bondi Icebergs pool",
                    "Beach volleyball courts"
                ],
                "specific_steps": [
                    "Shoot surfers with telephoto compression against waves",
                    "Capture Icebergs pool with ocean backdrop",
                    "Silhouettes of beachgoers at sunset"
                ]
            },
            "great ocean road": {
                "genres": ["landscape", "coastal", "nature"],
                "suggested_spots": [
                    "Twelve Apostles at golden hour",
                    "Loch Ard Gorge",
                    "Gibson Steps beach access"
                ],
                "specific_steps": [
                    "Shoot Twelve Apostles with foreground rocks for depth",
                    "Capture wave motion with varying shutter speeds",
                    "Use leading lines from cliff edges into ocean"
                ]
            }
        }
        
        # 🌍 Keyword → generic fallback guides
        self.generic_guides = {
            "cbd": [
                "Look for architectural symmetry in modern buildings",
                "Capture commuter flow at peak times",
                "Shoot reflections in glass facades",
                "Find leading lines in streets and crosswalks"
            ],
            "downtown": [
                "Photograph street-level activity and crowds",
                "Look for reflections in storefronts",
                "Capture urban geometry and patterns"
            ],
            "city center": [
                "Scout for architectural details",
                "Capture pedestrian flow and gestures",
                "Look for contrast between old and new buildings"
            ],
            "park": [
                "Frame joggers or walkers under tree branches",
                "Photograph patterns in leaves or textures in bark",
                "Try telephoto compression of subjects against foliage",
                "Look for natural framing with branches"
            ],
            "garden": [
                "Focus on macro details of flowers and textures",
                "Capture pathways as leading lines",
                "Look for color contrasts in plantings"
            ],
            "beach": [
                "Shoot silhouettes of walkers against sunset",
                "Look for reflections in wet sand",
                "Use leading lines from shore into horizon",
                "Capture wave motion with varying shutter speeds"
            ],
            "coast": [
                "Photograph rock formations with wave action",
                "Use long exposure for smooth water effects",
                "Capture golden hour light on cliffs"
            ],
            "market": [
                "Capture gestures at stalls (buying/selling moments)",
                "Look for color pops in produce and textiles",
                "Shoot low-angle through hanging goods",
                "Photograph vendor portraits with environmental context"
            ],
            "bazaar": [
                "Focus on textures and patterns in goods",
                "Capture candid vendor interactions",
                "Look for dramatic lighting through market structures"
            ],
            "station": [
                "Photograph waiting passengers isolated against architecture",
                "Use 1/15s shutter for motion blur of passing trains",
                "Capture symmetry in platforms, escalators or signage",
                "Look for light beams and geometric patterns"
            ],
            "subway": [
                "Capture commuter flow and gestures",
                "Look for leading lines in tunnels and platforms",
                "Shoot motion blur of trains arriving/departing"
            ],
            "metro": [
                "Photograph architectural patterns and symmetry",
                "Capture candid moments of waiting passengers",
                "Use available light creatively"
            ],
            "airport": [
                "Capture departure/arrival board reflections",
                "Photograph silhouettes against large windows",
                "Look for geometric patterns in architecture"
            ],
            "terminal": [
                "Focus on human moments of greeting/farewell",
                "Capture architectural scale and symmetry",
                "Look for interesting light through large windows"
            ],
            "zoo": [
                "Animal close-ups with telephoto",
                "Capture natural behaviors and interactions",
                "Portraits framed by habitat elements"
            ],
            "wildlife": [
                "Use telephoto for intimate portraits",
                "Capture action and behavior sequences",
                "Look for eye contact and expressions"
            ],
            "safari": [
                "Emphasize scale with wide landscapes",
                "Capture animals in their natural habitat context",
                "Use golden hour for warm, dramatic light"
            ],
            "museum": [
                "Symmetry in architecture",
                "Details of exhibits (no flash)",
                "Environmental capture of visitors interacting with art"
            ],
            "gallery": [
                "Photograph visitors engaging with artwork",
                "Capture architectural details and lighting",
                "Look for reflections and shadows"
            ],
            "mountain": [
                "Layered landscape depth with foreground interest",
                "Golden hour side light for texture",
                "Use leading lines from trails or ridges"
            ],
            "hill": [
                "Capture sweeping vistas with foreground elements",
                "Look for patterns in terrain",
                "Use atmospheric perspective for depth"
            ],
            "lookout": [
                "Shoot panoramic landscapes",
                "Include human scale for perspective",
                "Capture changing light conditions"
            ],
            "waterfront": [
                "Capture reflections in calm water",
                "Shoot silhouettes at golden/blue hour",
                "Use piers/jetties as leading lines",
                "Photograph boats with telephoto compression"
            ],
            "harbour": [
                "Capture boat details and reflections",
                "Shoot long exposures for smooth water",
                "Look for leading lines from docks and piers"
            ],
            "marina": [
                "Photograph masts as repeating patterns",
                "Capture reflections in calm water",
                "Use boats as foreground interest for cityscapes"
            ],
            "forest": [
                "Look for light beams through trees",
                "Capture textures in bark and foliage",
                "Use trees as natural framing elements"
            ],
            "trail": [
                "Use path as leading line into scene",
                "Capture hikers for scale",
                "Look for interesting light through canopy"
            ],
            "cafe": [
                "Window light portraits of patrons",
                "Detail shots of coffee and food",
                "Capture ambient atmosphere and interactions"
            ],
            "restaurant": [
                "Environmental portraits with context",
                "Detail shots emphasizing textures and colors",
                "Capture candid dining moments"
            ],
            "mall": [
                "Architectural patterns and symmetry",
                "Candid shoppers and crowd flow",
                "Reflections in storefronts"
            ],
            "shopping": [
                "Capture retail displays creatively",
                "Photograph crowd interactions",
                "Look for color and pattern contrasts"
            ]
        }

        # Lens rationale mapping
        self.lens_rationale = {
            "35mm F2": "Versatile for street and environmental portraits; natural field of view; fast aperture for low light",
            "35mm": "Versatile for street and environmental portraits; natural field of view",
            "70-300mm": "Compression for cityscapes and distant subjects; isolates details; great for candid telephoto street and wildlife",
            "fixed ~40mm": "Compact and discreet for street; forces you to move; classic reportage focal length",
            "28mm": "Wide enough for context; great for environmental storytelling; classic street photography focal length",
            "50mm": "Natural perspective for portraits; fast aperture; mimics human eye view; excellent for film photography"
        }

        # Composition style prompts
        self.composition_prompts = {
            "street": [
                "Decisive moment gestures",
                "Reflections in windows/puddles",
                "Strong shadow geometry",
                "Overlapping subject layers (3+ planes)",
                "Leading lines from curbs/crosswalks",
                "Color blocking with clothing/signage",
                "Frame within frame (doorways, windows)"
            ],
            "portrait": [
                "Eye-level connection with subject",
                "Environmental context storytelling",
                "Negative space for breathing room",
                "Catchlights in eyes for life",
                "Subject-background separation (shallow DOF)",
                "Rule of thirds eye placement",
                "Natural framing with foreground elements"
            ],
            "cityscape": [
                "Skyline compression with telephoto",
                "Symmetry in buildings/bridges",
                "Leading roads into vanishing point",
                "Blue hour balance (ambient + artificial light)",
                "Reflections after rain on streets",
                "Human scale reference for size",
                "Geometric patterns in architecture"
            ],
            "night street": [
                "Neon signs as key light source",
                "Motion blur at 1/10-1/30s for cars",
                "Headlight/taillight streaks",
                "Puddle reflections doubling lights",
                "Lit signage as colorful background",
                "High-ISO grain for atmosphere",
                "Silhouettes against lit windows"
            ],
            "architecture": [
                "Leading lines to vanishing point",
                "Symmetry and patterns",
                "Detail isolation (textures, materials)",
                "Wide context establishing shots",
                "Low angle for dramatic perspective",
                "Human scale reference",
                "Light and shadow interplay"
            ],
            "nature": [
                "Foreground interest for depth",
                "Golden hour side/back lighting",
                "Telephoto compression of layers",
                "Macro details of textures",
                "Rule of thirds horizon placement",
                "Natural framing with branches",
                "Leading lines with paths/rivers"
            ],
            "wildlife": [
                "Frame habitat context",
                "Tight telephoto detail on eyes",
                "Silhouettes at sunset",
                "Behavior/motion capture",
                "Animal eye contact for connection",
                "Environmental storytelling",
                "Action sequences with burst mode"
            ],
            "landscape": [
                "Foreground, midground, background layers",
                "Golden hour warm light",
                "Leading lines into scene",
                "Rule of thirds horizon",
                "Atmospheric perspective for depth",
                "Dramatic sky as key element",
                "Reflections in water"
            ],
            "beach": [
                "Silhouettes against sunset",
                "Reflections in wet sand",
                "Leading lines from shore",
                "Wave motion with shutter speed variation",
                "Foreground shells/rocks for depth",
                "Golden hour warm tones",
                "Minimalist compositions"
            ],
            "documentary": [
                "Candid unposed moments",
                "Environmental context",
                "Storytelling sequences",
                "Authentic expressions",
                "Details that reveal character",
                "Wide and tight shot variety",
                "Respectful distance and framing"
            ]
        }

    # 🔍 Analyze any location input (worldwide)
    def analyze_location(self, location):
        """Analyze location and return relevant shooting guide"""
        loc_lower = location.lower()
        
        # 1. Check for exact city/landmark matches
        for city in self.city_guides:
            if city in loc_lower:
                return self.city_guides[city]
        
        # 2. Check for generic keyword matches
        for keyword in self.generic_guides:
            if keyword in loc_lower:
                return {
                    "genres": [keyword],
                    "suggested_spots": [],
                    "specific_steps": self.generic_guides[keyword]
                }
        
        # 3. Universal fallback for any location
        return {
            "genres": ["documentary", "environmental"],
            "suggested_spots": [],
            "specific_steps": []
        }
    
    # 🏷️ POI Classification
    def classify_poi_category(self, tags):
        """Classify POI into photography-relevant category"""
        # Handle Google Places types
        if tags.get("type") == "google_place":
            types = tags.get("types", [])
            types_str = " ".join(types).lower()
            
            if any(x in types_str for x in ["park", "garden"]):
                return "park"
            if any(x in types_str for x in ["museum", "art_gallery"]):
                return "museum_art"
            if any(x in types_str for x in ["shopping_mall", "department_store"]):
                return "mall"
            if any(x in types_str for x in ["restaurant", "cafe", "bar"]):
                return "hospitality"
            if any(x in types_str for x in ["tourist_attraction", "point_of_interest"]):
                return "viewpoint"
            if any(x in types_str for x in ["beach", "natural_feature"]):
                return "coast"
            if any(x in types_str for x in ["bridge"]):
                return "bridge_pier"
            return "general"
        
        # Handle OSM tags
        t = tags.get("tourism","") + " " + tags.get("amenity","") + " " + tags.get("leisure","") + " " + tags.get("natural","") + " " + tags.get("man_made","") + " " + tags.get("shop","")
        t = t.lower()
        if "viewpoint" in t: return "viewpoint"
        if "museum" in t or "artwork" in t: return "museum_art"
        if "market" in t or "marketplace" in t: return "market"
        if "park" in t or "garden" in t: return "park"
        if "beach" in t or "coast" in t or "marina" in t: return "coast"
        if "bridge" in t or "pier" in t: return "bridge_pier"
        if "mall" in t or "department_store" in t: return "mall"
        if "cafe" in t or "restaurant" in t or "bar" in t: return "hospitality"
        return "general"

    def poi_task_templates(self, category, time_of_day, weather_summary):
        """Return steps and composition prompts tailored to POI category"""
        common = {
            "viewpoint": (
                [
                    "From the viewpoint, shoot 3 layered city/landscape frames with clear foreground",
                    "Use a longer focal length to compress the skyline; look for repeating patterns",
                    "Wait for a person entering frame to add scale",
                    "If windy, stabilize and try 1/10–1/30s motion blur of traffic/people"
                ],
                ["Layered depth", "Leading lines to horizon", "Human scale against vast scene", "Golden/blue hour glow"]
            ),
            "museum_art": (
                [
                    "Focus on symmetry and clean lines in exhibits and halls",
                    "Capture visitors interacting with exhibits (no flash)",
                    "Isolate textures and materials with tight framing",
                    "Use reflections in glass cases for layered abstracts"
                ],
                ["Symmetry", "Negative space", "Reflections", "Texture isolation"]
            ),
            "market": (
                [
                    "Capture buyer/seller gestures and exchanges",
                    "Shoot color pops of produce or textiles",
                    "Low angle through hanging items for depth",
                    "Wide environmental + tight detail pairs"
                ],
                ["Gesture/decisive moment", "Color blocking", "Frame within frame", "Leading lines through aisles"]
            ),
            "park": (
                [
                    "Use tree branches for natural framing",
                    "Macro details of leaves, bark, and textures",
                    "Silhouettes of runners/walkers at golden hour",
                    "Telephoto compression of layers of foliage"
                ],
                ["Natural frames", "Patterns in nature", "Silhouettes", "Foreground interest"]
            ),
            "coast": (
                [
                    "Experiment with shutter speeds for wave motion",
                    "Reflections in wet sand or puddles",
                    "Silhouettes against sunset/sunrise",
                    "Pier/marina structures as strong leading lines"
                ],
                ["Motion blur", "Reflections", "Minimalism", "Leading lines"]
            ),
            "bridge_pier": (
                [
                    "Centerline symmetry on the bridge/pier",
                    "Shoot from below/side for graphic geometry",
                    "Include passing subjects for scale/motion",
                    "Long exposure to smooth water if applicable"
                ],
                ["Symmetry", "Geometric patterns", "Scale with human element", "Long exposure water"]
            ),
            "mall": (
                [
                    "Architectural patterns and escalator geometry",
                    "Reflections in storefront glass",
                    "Candid shopper interactions",
                    "Top-down or low-angle abstracts"
                ],
                ["Repetition", "Reflections", "Leading lines", "Frame within frame"]
            ),
            "hospitality": (
                [
                    "Window light portraits (ask permission)",
                    "Detail shots of cups/plates with texture",
                    "Ambient scene with layered foreground",
                    "Reflections through window glass"
                ],
                ["Window light", "Texture details", "Layering", "Reflections"]
            ),
            "general": (
                [
                    "Scout and find the most distinctive visual elements",
                    "Shoot 1 wide, 3 medium, 3 tight frames for a mini-story",
                    "Look for symmetry, reflections, or bold shadows",
                    "Include at least 1 human element for scale/story"
                ],
                ["Wide–medium–tight sequencing", "Reflections", "Symmetry", "Human scale"]
            )
        }
        steps, prompts = common.get(category, common["general"])
        
        # Condition-aware tweaks
        if "rain" in weather_summary.lower() or "precipitation" in weather_summary.lower():
            steps = ["Use shelter and focus on reflections and umbrellas", "Shoot through glass for layered rainy scenes"] + steps
            prompts = list(set(prompts + ["Rain reflections", "Through-glass layering"]))
        if time_of_day in ["golden hour", "blue hour"]:
            prompts = list(set(prompts + ["Golden/blue hour color contrast"]))
        
        return steps, prompts
    
    # Generate exposure presets
    def generate_exposures(self, is_digital=True, film_iso="400", time_of_day=""):
        """Generate multiple exposure starting points"""
        if not is_digital:
            return [
                f"☀️ Sunny 16: f/16, 1/{film_iso}s, ISO {film_iso}",
                f"☁️ Overcast: f/8, 1/250s, ISO {film_iso}",
                f"🌳 Shade: f/5.6, 1/125s, ISO {film_iso}",
                f"🌅 Golden hour backlit: f/4, 1/500s, ISO {film_iso} (meter for highlights)",
                f"🌙 Night: f/2.8, 1/30s, ISO {film_iso} (consider push +1 stop)"
            ]
        
        base = [
            "☀️ Sunny: f/8, 1/500s, ISO 200",
            "☁️ Overcast: f/4, 1/250s, ISO 800",
            "🌳 Shade: f/2.8, 1/125s, ISO 1600"
        ]
        
        if time_of_day in ["golden hour", "blue hour"]:
            base.append("🌅 Golden/Blue hour: f/4, 1/250s, ISO Auto (cap 3200), -0.3 EV comp")
        
        if time_of_day == "night":
            base.append("🌙 Night: f/2, 1/60s, ISO 3200-6400, spot meter highlights")
        
        return base

    def get_composition_prompts(self, photo_type):
        """Get 5+ composition prompts based on photography type"""
        photo_type_lower = photo_type.lower()
        
        # Find matching prompt set
        for key in self.composition_prompts:
            if key in photo_type_lower:
                prompts = self.composition_prompts[key]
                return random.sample(prompts, min(5, len(prompts)))
        
        # Default prompts
        return [
            "Rule of thirds placement",
            "Foreground interest for depth",
            "Leading lines to subject",
            "Negative space for breathing room",
            "Frame within frame"
        ]

    def is_recent_repeat(self, new_task, history, window=7):
        """Check if location+type occurred in last N tasks (weekly window)"""
        if not history: 
            return False
        
        try:
            loc_type = (
                new_task.get("photo_type", "").lower(), 
                new_task.get("when_where", "").split("|")[-1].strip().lower()
            )
            
            recent = []
            for t in history[-window:]:
                # Skip tasks missing required keys
                if not t.get("photo_type") or not t.get("when_where"):
                    continue
                
                recent.append((
                    t["photo_type"].lower(), 
                    t["when_where"].split("|")[-1].strip().lower()
                ))
            
            return loc_type in recent
        except Exception as e:
            # If any error occurs, just return False (don't block task generation)
            return False

    def generate_variation(self, base_task):
        """Force refresh of steps, exposures, and prompts for variation"""
        task = dict(base_task)  # shallow copy

        # Shuffle steps if >3
        if len(task["steps"]) > 3:
            random.shuffle(task["steps"])

        # Shuffle exposures
        if len(task["exposure_presets"]) > 3:
            exp = task["exposure_presets"][:]
            random.shuffle(exp)
            task["exposure_presets"] = exp[:min(4, len(exp))]

        # Always resample prompts
        if len(task["composition_prompts"]) > 1:
            task["composition_prompts"] = random.sample(
                task["composition_prompts"],
                len(task["composition_prompts"])
            )

        # Tag as variation
        task["title"] += " (Weekly Variation)"
        task["summary"] += " | Rotated creative variation for repeat location."
        
        return task

    def get_safety_note(self, params):
        """Generate contextual safety note"""
        photo_type = params['photo_type'].lower()
        location = params['location'].lower()
        
        if 'street' in photo_type or 'street' in location or 'cbd' in location:
            return "⚠️ Stay aware of traffic; keep camera strap on; be respectful and discreet with subjects"
        elif 'portrait' in photo_type:
            return "⚠️ Obtain clear consent before shooting; respect personal boundaries and comfort"
        elif 'night' in params['time_of_day'] or 'night' in photo_type:
            return "⚠️ Stay in well-lit public areas; be aware of surroundings; secure your gear"
        elif any(word in location for word in ['museum', 'gallery', 'mall']):
            return "⚠️ Check venue policies (no flash/tripod often); respect restricted areas and staff directions"
        else:
            return "⚠️ Be respectful of people and property; ask permission when photographing private spaces"

    def generate_success_criteria(self, params):
        """Generate measurable success criteria scaled by duration"""
        photo_type = params['photo_type'].lower()
        duration = params['duration']
        
        # Base keeper count scales with duration
        if duration <= 60:
            keeper_count = "10+"
        elif duration <= 120:
            keeper_count = "15+"
        elif duration <= 240:
            keeper_count = "25+"
        else:
            keeper_count = "40+"
        
        criteria_map = {
            "street": [
                "✓ 1 decisive moment with clear gesture/action",
                "✓ 1 layered frame with 3+ depth planes",
                "✓ 1 reflection or strong shadow composition",
                f"✓ {keeper_count} keeper frames total"
            ],
            "portrait": [
                "✓ Sharp focus on eyes in at least 3 frames",
                "✓ 1 frame with clean background separation",
                "✓ Natural expression captured (not forced)",
                "✓ Catchlights visible in eyes",
                f"✓ {keeper_count} keepers with good light"
            ],
            "cityscape": [
                "✓ 1 wide establishing shot with context",
                "✓ 1 detail shot isolating pattern/texture",
                "✓ Straight verticals (no keystoning)",
                "✓ 1 frame with human scale reference",
                f"✓ {keeper_count} keeper frames"
            ],
            "architecture": [
                "✓ Strong leading lines in at least 2 frames",
                "✓ 1 symmetrical composition",
                "✓ Detail and context shots both captured",
                f"✓ {keeper_count} keepers"
            ],
            "wildlife": [
                "✓ Sharp focus on animal eyes in 3+ frames",
                "✓ 1 behavior/action shot",
                "✓ 1 environmental context shot",
                f"✓ {keeper_count} keeper frames"
            ],
            "landscape": [
                "✓ Foreground, midground, background in 2+ frames",
                "✓ 1 frame with dramatic sky",
                "✓ Sharp focus throughout (use smaller aperture)",
                f"✓ {keeper_count} keeper frames"
            ]
        }
        
        for key, criteria in criteria_map.items():
            if key in photo_type:
                return criteria
        
        # Default
        return [
            "✓ 3+ strong compositions following prompts",
            "✓ Consistent exposure across series",
            "✓ At least 1 frame exceeding expectations",
            f"✓ {keeper_count} keeper frames"
        ]

    def generate_contingencies(self, params):
        """Generate smart contingency plans"""
        contingencies = []
        
        weather = params.get('weather', 'clear')
        if weather == 'rain':
            contingencies.append("☔ Rain intensifies → focus on reflections in puddles and umbrella abstracts")
        elif weather == 'overcast':
            contingencies.append("☁️ Overcast is ideal for portraits and textures; emphasize soft even light")
        elif weather == 'fog':
            contingencies.append("🌫️ Fog → switch to minimalism, silhouettes, layered depth fades")
        
        if params['time_of_day'] in ['golden hour', 'blue hour']:
            contingencies.append("⏰ Light fades quickly → increase ISO or move to artificially lit areas")
        
        if 'street' in params['photo_type'].lower():
            contingencies.append("🚶 Location quiet → move to busier intersection, transit hub, or café")
        
        if not contingencies:
            contingencies.append("🔄 Conditions change → adapt subject while keeping same gear/approach")
        
        return " | ".join(contingencies)

    def generate_task(self, params, history):
        """Generate complete enriched task with worldwide location support + POI intelligence"""
        
        # 🌍 Try to geocode and fetch POIs
        geo = geocode_location(params["location"])
        poi = None
        poi_steps = []
        poi_prompts = []
        weather_summary = ""
        
        if geo:
            with st.spinner(f"🔍 Finding nearby points of interest... (via {geo.get('source', 'API')})"):
                pois = fetch_pois(geo["lat"], geo["lon"], radius_m=800)
                
                # Get weather
                weather_summary = get_weather(geo["lat"], geo["lon"])
                
                # Avoid repeating same POI same day
                used_poi_ids_today = set()
                today_str = datetime.now().strftime("%Y-%m-%d")
                for t in history:
                    if t.get("date","").startswith(today_str) and t.get("poi_id"):
                        used_poi_ids_today.add(t["poi_id"])
                
                # Choose first unused named POI
                candidate = None
                for p in pois:
                    if p["id"] in used_poi_ids_today:
                        continue
                    if p["name"]:
                        candidate = p
                        break
                
                # Fallback to any unused
                if not candidate and pois:
                    for p in pois:
                        if p["id"] not in used_poi_ids_today:
                            candidate = p
                            break
                
                if candidate:
                    category = self.classify_poi_category(candidate["tags"])
                    poi_steps, poi_prompts = self.poi_task_templates(category, params["time_of_day"], weather_summary)
                    poi = candidate
        
        # Fallback to static location guides
        loc_data = self.analyze_location(params["location"])
        
        # Duration-scaled base steps
        base_steps = [
            "Scout area for 5–10 minutes",
            "Shoot 1 wide establishing shot",
            "Capture 3 strong details/textures",
            "Find 2 human/motion moments",
            "Experiment with 2 unusual angles"
        ]

        # Scale checklist length by duration
        if params["duration"] > 60:
            base_steps += [
                "Create 1 storytelling sequence of 3–5 frames",
                "Look for reflections and abstract compositions"
            ]
        if params["duration"] > 120:
            base_steps += [
                "Photograph a subject from 3 different perspectives (near/mid/far)",
                "Dedicate 15 mins to a single scene, working multiple variations"
            ]
        if params["duration"] > 240:
            base_steps += [
                "Focus on a thematic series (shadows, reflections, gestures, etc.)",
                "Build a mini-project: 12 images that could tell a story together",
                "Review work mid-session and adjust approach"
            ]

        # Combine POI-specific + location-specific + base steps
        steps_loc_specific = poi_steps if poi_steps else loc_data.get("specific_steps", [])[:]
        if steps_loc_specific:
            steps = steps_loc_specific[:min(5, len(steps_loc_specific))] + base_steps
        else:
            steps = base_steps

        # Add POI header if present
        if poi:
            poi_name = poi.get('name','(Unnamed)')
            header = f"📍 Focus location: {poi_name}"
            steps.insert(0, header)

        # Add suggested spots to the very beginning (if available from static guides)
        if loc_data.get("suggested_spots"):
            spots_text = "📍 Suggested spots: " + ", ".join(loc_data["suggested_spots"][:3])
            steps.insert(0, spots_text)

        exposures = self.generate_exposures(
            params["is_digital"], 
            params.get("film_iso", "400"), 
            params["time_of_day"]
        )
        
        # Merge POI prompts with type-based prompts
        comp_prompts = self.get_composition_prompts(params["photo_type"])
        if poi_prompts:
            comp_prompts = list(set(comp_prompts + poi_prompts))[:7]  # max 7 prompts

        # Build gear string
        gear = f"{params['camera']} + {params['lens']}; {params['color_mode']}"
        if params['is_digital']:
            gear += "; RAW+JPEG recommended"
        else:
            gear += f"; {params.get('film_stock', 'Film')} @ ISO {params.get('film_iso', '400')}"

        task = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "title": f"{params['time_of_day'].title()} {params['photo_type'].title()} @ {params['location']}",
            "summary": f"{params['photo_type']} session in {params['location']} | {params['camera']} + {params['lens']} | {params['duration']} mins | Checklist: {len(steps)} steps",
            "when_where": f"{params['time_of_day'].title()} ({params['duration']} min) | {params['location']}",
            "photo_type": params["photo_type"],
            "camera": params["camera"],
            "lens": params["lens"],
            "gear": gear,
            "lens_rationale": self.lens_rationale.get(params["lens"], "General-purpose lens for this task"),
            "exposure_presets": exposures,
            "steps": steps,
            "composition_prompts": comp_prompts,
            "contingencies": self.generate_contingencies(params),
            "success_criteria": self.generate_success_criteria(params),
            "safety_note": self.get_safety_note(params),
            "color_mode": params['color_mode'],
            "poi_id": poi["id"] if poi else "",
            "poi_name": poi.get("name","") if poi else "",
            "poi_category": self.classify_poi_category(poi["tags"]) if poi else "",
            "poi_coords": {"lat": poi["lat"], "lon": poi["lon"]} if poi else None,
            "weather_summary": weather_summary
        }

        # Weekly rotation enforcement
        if self.is_recent_repeat(task, history, window=7):
            task = self.generate_variation(task)

        return task

# -------------------------------
# PWA Manifest + Service Worker injection
# -------------------------------
st.markdown("""
<link rel="manifest" href="/manifest.json">
<script>
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/service-worker.js')
    .then(reg => console.log('SW registered:', reg.scope))
    .catch(err => console.error('SW failed:', err));
}
</script>
""", unsafe_allow_html=True)

# -------------------------------
# UI Configuration
# -------------------------------
st.set_page_config(
    page_title="📷 Daily Photo Task",
    page_icon="📷",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize planner
planner = PhotoTaskPlanner()

# Navigation
page = st.sidebar.radio("📂 Navigate", ["Planner", "History"])

# -------------------------------
# Planner Page
# -------------------------------
if page == "Planner":
    st.title("📷 Daily Photography Task Planner")
    st.markdown("*Generate detailed, location-aware photography tasks tailored to your gear and conditions — works anywhere in the world.*")

    st.sidebar.header("📋 Today's Setup")
    
    photo_type = st.sidebar.text_input("📸 Photography Type", "street", help="e.g., street, portrait, cityscape, night street, wildlife, landscape")
    location = st.sidebar.text_input("📍 Location", "Melbourne CBD", help="Any location worldwide (e.g., Melbourne CBD, Tokyo Shibuya, Central Park NYC, local café)")
    
    camera = st.sidebar.selectbox("📷 Camera", ["Fujifilm X-T5", "Ricoh GR IIIx", "Nikon FE2", "Pentax ME Super"])

    if camera == "Ricoh GR IIIx":
        lens = "fixed ~40mm"
    elif camera == "Fujifilm X-T5":
        lens = st.sidebar.selectbox("🔍 Lens", ["35mm F2", "70-300mm"])
    else:
        lens = st.sidebar.selectbox("🔍 Lens", ["28mm", "50mm"])

    time_of_day = st.sidebar.selectbox("🕐 Time of Day", ["morning", "midday", "golden hour", "blue hour", "night"])
    duration = st.sidebar.slider("⏱️ Duration (mins)", 15, 360, 30)
    lighting = st.sidebar.selectbox("💡 Lighting", ["daylight", "shade", "mixed", "artificial"])
    
    if "home" not in location.lower() and "indoor" not in location.lower():
        weather = st.sidebar.selectbox("🌦️ Weather", ["clear", "cloudy", "overcast", "rain", "fog", "windy"])
    else:
        weather = "indoor"
    
    color_mode = st.sidebar.radio("🎨 Color Mode", ["Color", "Black & White"])

    is_digital = camera in ["Fujifilm X-T5", "Ricoh GR IIIx"]
    film_stock, film_iso = "", ""
    
    if not is_digital:
        st.sidebar.markdown("---")
        st.sidebar.markdown("**🎞️ Film Settings**")
        
        # Smart film stock selection based on color mode
        if color_mode == "Black & White":
            film_options = [
                "Ilford HP5 Plus 400",
                "Kodak Tri-X 400",
                "Ilford FP4 Plus 125",
                "Kodak T-Max 400",
                "Ilford Delta 3200",
                "Fomapan 400",
                "Kodak Double-X 250"
            ]
        else:  # Color
            film_options = [
                "Kodak Portra 400",
                "Kodak Portra 160",
                "Kodak Portra 800",
                "Fujifilm Pro 400H",
                "Kodak Ektar 100",
                "Fujifilm Superia 400",
                "Cinestill 800T",
                "Kodak Gold 200",
                "Fujifilm Velvia 50"
            ]
        
        film_stock = st.sidebar.selectbox("Film Stock", film_options, index=0)
        
        # Auto-extract ISO from film name, or allow manual override
        iso_from_name = ''.join(filter(str.isdigit, film_stock.split()[-1]))
        film_iso = st.sidebar.text_input("Film ISO", iso_from_name if iso_from_name else "400")
    
    constraints = st.sidebar.text_area("⚖️ Constraints/Preferences", "Stay local, avoid crowds")

    if st.button("🎯 Generate Today's Task", type="primary"):
        params = {
            "photo_type": photo_type,
            "location": location,
            "camera": camera,
            "lens": lens,
            "time_of_day": time_of_day,
            "duration": duration,
            "lighting": lighting,
            "weather": weather,
            "color_mode": color_mode,
            "is_digital": is_digital,
            "film_stock": film_stock,
            "film_iso": film_iso,
            "constraints": constraints
        }
        
        # Load history and generate task
        history = load_history()
        task = planner.generate_task(params, history)
        save_task(task)

        st.success("✅ Task generated and saved to history!")
        
        st.markdown("---")
        st.header(f"📋 {task['title']}")
        st.markdown(f"*{task['summary']}*")
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**⏰ When/Where:** {task['when_where']}")
        with col2:
            st.markdown(f"**📷 Gear:** {task['gear']}")
        
        if task.get('poi_name'):
            st.info(f"**📍 Focus POI:** {task['poi_name']} ({task.get('poi_category','')})")
        
        if task.get('weather_summary'):
            st.info(f"**🌦️ Current conditions:** {task['weather_summary']}")
        
        st.info(f"**🔍 Why this lens?** {task['lens_rationale']}")

        st.markdown("### ⚙️ Exposure Presets")
        for preset in task["exposure_presets"]:
            st.markdown(f"- {preset}")

        st.markdown("### ✅ Step-by-Step Checklist")
        for i, step in enumerate(task["steps"], 1):
            st.markdown(f"{i}. {step}")

        st.markdown("### 🎨 Composition Prompts")
        for p in task["composition_prompts"]:
            st.markdown(f"- {p}")

        st.markdown("### 🔄 Contingencies")
        st.warning(task["contingencies"])

        st.markdown("### 🎯 Success Criteria")
        for c in task["success_criteria"]:
            st.markdown(c)

        st.markdown("### ⚠️ Safety & Respect")
        st.error(task['safety_note'])

# -------------------------------
# History Page
# -------------------------------
if page == "History":
    st.title("📚 Task History")
    st.markdown("*Your last 7 photography tasks*")
    
    history = load_history()
    
    if not history:
        st.info("📭 No tasks saved yet. Generate your first task to begin tracking!")
    else:
        for i, task in enumerate(reversed(history), 1):
            with st.expander(f"**{i}.** {task['date']} — {task['title']}", expanded=(i==1)):
                st.markdown(f"**Summary:** {task['summary']}")
                st.markdown(f"**When/Where:** {task['when_where']}")
                
                # Fixed gear display
                gear_display = task.get('gear', task.get('camera', '') + ' + ' + task.get('lens', ''))
                st.markdown(f"**Gear:** {gear_display}")
                
                if task.get('poi_name'):
                    st.markdown(f"**📍 Focus POI:** {task['poi_name']} ({task.get('poi_category','')})")
                
                if task.get('weather_summary'):
                    st.markdown(f"**🌦️ Conditions:** {task['weather_summary']}")
                
                st.markdown("**Exposure Presets:**")
                for preset in task.get("exposure_presets", []):
                    st.markdown(f"- {preset}")
                
                st.markdown("**Steps:**")
                for j, step in enumerate(task.get("steps", []), 1):
                    st.markdown(f"{j}. {step}")
                
                st.markdown("**Composition Prompts:**")
                for prompt in task.get("composition_prompts", []):
                    st.markdown(f"- {prompt}")
                
                st.markdown("**Success Criteria:**")
                for criterion in task.get("success_criteria", []):
                    st.markdown(criterion)