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
class PhotoTaskPlanner:
    def __init__(self):
        self.composition_prompts = {
            "street": ["gestures", "reflections in windows", "strong shadows"],
            "portrait": ["eye-level connection", "frame with context", "clean background"],
            "cityscape": ["leading lines", "symmetry", "human scale for size"],
            "night street": ["neon lights", "puddle reflections", "motion blur of cars"],
        }

    def generate_exposure_settings(self, params):
        if not params["is_digital"]:
            iso = params.get("film_iso", "400")
            return f"Sunny 16 baseline. Start f/8 1/250s @ ISO {iso}"
        else:
            return {
                "golden hour": "f/4, 1/500s, ISO Auto (cap 3200)",
                "blue hour": "f/2.8, 1/125s, ISO Auto (cap 6400)",
                "night": "f/2, 1/60s, ISO 6400",
                "midday": "f/8, 1/500s, ISO Auto (cap 1600)",
                "morning": "f/5.6, 1/250s, ISO Auto (cap 3200)"
            }.get(params["time_of_day"], "f/5.6, 1/250s, ISO Auto")
    
    def get_composition_prompts(self, photo_type):
        for key in self.composition_prompts:
            if key in photo_type:
                return random.sample(self.composition_prompts[key], min(3, len(self.composition_prompts[key])))
        return ["rule of thirds", "foreground interest", "symmetry/asymmetry"]

    def generate_steps(self, params):
        base = [f"Go to {params['location']} and observe lighting."]
        if "street" in params["photo_type"]:
            base.extend(["Shoot 3 mini sequences of activity", "Look for reflections", "Capture gestures/decisive moments"])
        elif "portrait" in params["photo_type"]:
            base.extend(["Set subject near light source", "Shoot at eye-level", "Capture multiple expressions"])
        else:
            base.extend(["Find 3-5 subjects", "Shoot from multiple angles"])
        if params["is_digital"]:
            base.append("Review histograms/focus and adjust")
        else:
            base.append("Record exposures, rewind & label film")
        return base[:6]

    def generate_task(self, params):
        title = f"{params['time_of_day'].title()} {params['photo_type'].title()} at {params['location']}"
        summary = f"Practice {params['photo_type']} using {params['camera']} with {params['lens']} in {params['color_mode']} mode."
        gear = f"{params['camera']} + {params['lens']}; {params['color_mode']}"
        if params['is_digital']:
            gear += "; RAW+JPEG"
        else:
            gear += f"; {params['film_stock']} ISO {params['film_iso']}"
        task = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "title": title,
            "summary": summary,
            "when_where": f"{params['time_of_day']} for {params['duration']} mins | {params['location']}",
            "gear": gear,
            "exposure_start": self.generate_exposure_settings(params),
            "steps": self.generate_steps(params),
            "composition_prompts": self.get_composition_prompts(params["photo_type"]),
            "contingencies": "If weather changes, switch subjects but keep same gear.",
            "success_criteria": ["1 strong keeper", "Try all prompts", "10+ usable frames"],
            "safety_note": "Stay aware of surroundings; respect people & property."
        }
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