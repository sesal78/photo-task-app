import streamlit as st
import json
import os
import random
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
# Simple Photo Task Planner Core
# -------------------------------
import random
from datetime import datetime

class PhotoTaskPlanner:
    def __init__(self):
        # 🎯 Pre-built location dictionaries (AU + examples)
        self.city_guides = {
            "melbourne cbd": {
                "genres": ["street", "cityscape"],
                "suggested_spots": [
                    "Flinders Street Station for architecture + people flow",
                    "Hosier Lane graffiti",
                    "Trams on Bourke Street",
                    "Southbank for skylines"
                ],
                "specific_steps": [
                    "Shoot tram motion blur at 1/15s shutter",
                    "Capture layered crossing at Flinders",
                    "Frame graffiti walls with passerby",
                    "Reflections on glass facades"
                ]
            },
            "geelong": {
                "genres": ["cityscape","urban nature"],
                "suggested_spots": ["Geelong Waterfront","Eastern Beach boardwalk","Cunningham Pier"],
                "specific_steps": [
                    "Shoot bollard sculptures as foreground subjects",
                    "Capture pier symmetry leading into horizon",
                    "Reflections in water at golden hour"
                ]
            },
            "sydney": {
                "genres": ["cityscape","architecture"],
                "suggested_spots": ["Opera House","Circular Quay","The Rocks"],
                "specific_steps": [
                    "Wide shots of Opera House at golden hour",
                    "Reflections at Circular Quay",
                    "Historic textures at The Rocks"
                ]
            },
            "toronga zoo": {
                "genres": ["wildlife","portrait"],
                "suggested_spots": ["Giraffe outlook", "Elephant trail", "Seal show"],
                "specific_steps": [
                    "Capture giraffes with Harbour Bridge behind",
                    "Elephant texture studies with telephoto",
                    "Seal freeze-frame action shots"
                ]
            }
            # ➕ Add more as needed (Cairns, Brisbane, Perth, etc.)
        }

        # 🌍 Keyword → generic fallback guides
        self.generic_guides = {
            "cbd": ["Capture commuters crossing streets", "Look for reflections in glass", "Photograph trams/buses with motion blur"],
            "park": ["Photograph joggers framed under trees", "Textures in bark/leaves", "Wide shot showing open space"],
            "beach": ["Silhouette against sunset", "Reflections in wet sand", "Leading shoreline lines"],
            "market": ["Vendor-customer handover gestures", "Colors in fruit/vegetable stalls", "Candid bustling crowds"],
            "station": ["1/15s motion blur of trains", "Geometric leading lines of platforms", "Candid portraits of commuters"],
            "zoo": ["Animal close-ups with telephoto", "Capture natural behaviors", "Portraits framed by habitat elements"],
            "museum": ["Symmetry in architecture", "Details of exhibits (no flash)", "Environmental capture of visitors"],
            "mountain": ["Layered landscape depth", "Foreground interest with rocks/plants", "Golden hour side light"]
        }

        # Lens rationale mapping
        self.lens_rationale = {
            "35mm": "Versatile for street and environment; balances context + subject",
            "70-300mm": "Compression & detail isolation; wildlife, skyline or candid distance shots",
            "fixed ~40mm": "Compact, discreet, perfect for documentary-style street",
            "28mm": "Wide angle storytelling; great for environmental portraits & streets",
            "50mm": "Natural perspective portraits; fast aperture, classic rendering"
        }

        # Composition style prompts
        self.composition_prompts = {
            "street": ["Gestures/decisive moments","Reflections","Strong shadows","Overlapping planes","Color blocking"],
            "portrait": ["Catchlights in eyes","Negative space","Environmental context","Subject-background separation","Natural framing"],
            "cityscape": ["Skyline symmetry","Blue hour balance","Leading roads","Reflections","Human scale vs structures"],
            "wildlife": ["Frame habitat context","Tight telephoto detail","Silhouettes at sunset","Behavior/motion capture","Animal eye contact"],
            "nature": ["Golden hour light","Layered landscapes","Macro close-ups","Foreground framing","Natural textures"]
        }

    # 🔍 Analyze any location input (worldwide)
    def analyze_location(self, location):
        loc_lower = location.lower()
        # 1. Known exact matches
        for city in self.city_guides:
            if city in loc_lower:
                return self.city_guides[city]
        # 2. Smart keyword matches
        for key in self.generic_guides:
            if key in loc_lower:
                return {"genres":[key], "specific_steps": self.generic_guides[key]}
        # 3. Universal fallback
        return {
            "genres":["documentary","environmental"],
            "specific_steps":[
                f"Scout {location} for unique features",
                "Find an establishing wide shot",
                "Shoot details that tell the story of this place",
                "Look for candid human activity that adds local flavor"
            ]
        }
    
    # Exposures: give multiple starting points
    def generate_exposures(self, is_digital=True, film_iso="400", time_of_day="",):
        if not is_digital:
            return [
                f"Sunny16 (f/16, 1/{film_iso} s, ISO {film_iso})",
                f"Overcast f/8, 1/250s, ISO {film_iso}",
                f"Shade f/5.6, 1/125s, ISO {film_iso}",
                f"Golden hr f/4, 1/250s, ISO {film_iso}",
                f"Night f/2, 1/30s, ISO {film_iso} + consider push"
            ]
        base = [
            "☀️ Sunny: f/8, 1/500s, ISO 200",
            "☁️ Overcast: f/4, 1/250s, ISO 800",
            "🌳 Shade: f/2.8, 1/125s, ISO 1600"
        ]
        if time_of_day in ["golden hour","blue hour"]:
            base += ["🌅 Golden hr: f/4, 1/250s, ISO auto ≤3200"]
        if "night" in time_of_day:
            base += ["🌙 Night: f/2, 1/60s, ISO 3200-6400"]
        return base
    
    def get_composition_prompts(self, photo_type):
        photo_type = photo_type.lower()
        for key in self.composition_prompts:
            if key in photo_type:
                return random.sample(self.composition_prompts[key], min(5,len(self.composition_prompts[key])))
        return ["Rule of thirds","Leading lines","Negative space","Foreground interest","Symmetry"]

    # 🚫 Duplicate task prevention
    def is_duplicate(self, new_task, history):
        if not history: return False
        last_task = history[-1]
        return (new_task["photo_type"] == last_task["photo_type"] 
                and new_task["when_where"].split("|")[-1].strip().lower() 
                == last_task["when_where"].split("|")[-1].strip().lower())

    # Task generator
    def generate_task(self, params, history):
        loc_data = self.analyze_location(params["location"])
        steps = loc_data["specific_steps"][:]
        
        # Always different composition prompts
        comp_prompts = self.get_composition_prompts(params["photo_type"])
        exposures = self.generate_exposures(params["is_digital"], params.get("film_iso","400"), params["time_of_day"])

        task = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "title": f"{params['time_of_day'].title()} {params['photo_type'].title()} @ {params['location']}",
            "summary": f"{params['photo_type']} session in {params['location']} | {params['camera']} + {params['lens']} | {params['duration']} mins",
            "when_where": f"{params['time_of_day'].title()} ({params['duration']} min) | {params['location']}",
            "photo_type": params["photo_type"],
            "camera": params["camera"],
            "lens": params["lens"],
            "lens_rationale": self.lens_rationale.get(params["lens"],"General purpose lens"),
            "exposure_presets": exposures,
            "steps": steps,
            "composition_prompts": comp_prompts,
            "contingencies": "Adapt to crowd density, lighting, and weather changes",
            "success_criteria": ["✓ 1 strong storytelling frame","✓ 1 reflection/texture","✓ 10+ keeper shots"],
            "safety_note": "⚠️ Always respect people, property, and stay aware of surroundings"
        }

        # Duplicate prevention: re-roll comp prompts if duplicate
        while self.is_duplicate(task, history):
            task["composition_prompts"] = self.get_composition_prompts(params["photo_type"])
        
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
# UI Navigation
# -------------------------------
st.set_page_config(page_title="📷 Daily Photo Task", layout="wide")
page = st.sidebar.radio("📂 Navigate", ["Planner", "History"])

planner = PhotoTaskPlanner()

# -------------------------------
# Planner Page
# -------------------------------
if page == "Planner":
    st.title("📷 Daily Photography Task Planner")

    photo_type = st.sidebar.text_input("Photography Type", "street")
    location = st.sidebar.text_input("Location", "neighborhood")
    camera = st.sidebar.selectbox("Camera", ["Fujifilm X-T5","Ricoh GR IIIx","Nikon FE2","Pentax ME Super"])

    if camera == "Ricoh GR IIIx":
        lens = "fixed ~40mm"
    elif camera == "Fujifilm X-T5":
        lens = st.sidebar.selectbox("Lens", ["35mm F2", "70-300mm"])
    else:
        lens = st.sidebar.selectbox("Lens", ["28mm","50mm"])

    time_of_day = st.sidebar.selectbox("Time of Day", ["morning","midday","golden hour","blue hour","night"])
    duration = st.sidebar.slider("Duration (mins)", 15, 45, 30)
    lighting = st.sidebar.selectbox("Lighting", ["daylight","shade","mixed","artificial"])
    weather = st.sidebar.selectbox("Weather", ["clear","cloudy","overcast","rain","fog"]) if "home" not in location.lower() else "indoor"
    color_mode = st.sidebar.radio("Color Mode", ["Color","Black & White"])

    is_digital = camera in ["Fujifilm X-T5","Ricoh GR IIIx"]
    film_stock, film_iso = "", ""
    if not is_digital:
        film_stock = st.sidebar.text_input("Film Stock", "Portra 400")
        film_iso = st.sidebar.text_input("Film ISO", "400")
    constraints = st.sidebar.text_area("Constraints", "Stay local, avoid crowds")

    if st.button("Generate Task 🎯"):
        params = {
            "photo_type": photo_type, "location": location,
            "camera": camera, "lens": lens, "time_of_day": time_of_day,
            "duration": duration, "lighting": lighting, "weather": weather,
            "color_mode": color_mode, "is_digital": is_digital,
            "film_stock": film_stock, "film_iso": film_iso,
            "constraints": constraints
        }
        task = planner.generate_task(params)
        save_task(task)

        st.subheader(task["title"])
        st.write(f"**Summary:** {task['summary']}")
        st.write(f"**When/Where:** {task['when_where']}")
        st.write(f"**Gear:** {task['gear']}")
        st.write(f"**Exposure Start:** {task['exposure_start']}")

        st.markdown("### ✅ Steps")
        for i, step in enumerate(task["steps"], 1):
            st.markdown(f"{i}. {step}")

        st.markdown("### 🎨 Composition Prompts")
        for p in task["composition_prompts"]:
            st.markdown(f"- {p}")

        st.markdown("### 🔄 Contingencies")
        st.info(task["contingencies"])

        st.markdown("### 🎯 Success Criteria")
        for c in task["success_criteria"]:
            st.markdown(f"- {c}")

        st.warning(f"⚠️ {task['safety_note']}")

# -------------------------------
# History Page
# -------------------------------
if page == "History":
    st.title("📚 Task History (Last 7 Tasks)")
    history = load_history()
    if not history:
        st.info("No tasks saved yet. Generate one to begin!")
    else:
        for i, task in enumerate(reversed(history), 1):
            with st.expander(f"{i}. {task['date']} – {task['title']}"):
                st.write(f"**Summary:** {task['summary']}")
                st.write(f"**When/Where:** {task['when_where']}")
                st.write(f"**Gear:** {task['gear']}")
                st.write("### Steps")
                st.write("\n".join([f"{j+1}. {s}" for j,s in enumerate(task["steps"])]))