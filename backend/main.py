"""FastAPI service for the Personalized Travel Itinerary Planner."""
from __future__ import annotations
import json, os, sqlite3, uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / '.env')
DB_PATH = Path(os.getenv('SQLITE_PATH', BASE / 'trips.db'))
app = FastAPI(title='Wanderwise Travel Planner', version='1.0.0')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=False, allow_methods=['*'], allow_headers=['*'])

class PlanRequest(BaseModel):
    destination: str = Field(min_length=2, max_length=100)
    start_date: date
    end_date: date
    budget: int = Field(ge=1000, le=10_000_000)
    travelers: int = Field(default=1, ge=1, le=30)
    interests: list[str] = Field(default_factory=list, max_length=8)
    pace: str = Field(default='Balanced', pattern='^(Relaxed|Balanced|Packed)$')
    travel_style: str = Field(default='Comfort', max_length=40)
    currency: str = Field(default='INR', pattern='^(INR|USD|EUR)$')

    @model_validator(mode='after')
    def dates_valid(self):
        if self.end_date < self.start_date:
            raise ValueError('End date must be on or after start date.')
        if (self.end_date - self.start_date).days > 13:
            raise ValueError('Please choose a trip of 14 days or fewer.')
        return self

class SaveRequest(BaseModel):
    trip: dict[str, Any]


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS trips (id TEXT PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, destination TEXT NOT NULL, payload TEXT NOT NULL, workspace_id TEXT NOT NULL DEFAULT \'legacy\')')
    columns={row[1] for row in conn.execute('PRAGMA table_info(trips)').fetchall()}
    if 'workspace_id' not in columns:
        conn.execute("ALTER TABLE trips ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'legacy'")
    return conn


def _safe_json(text: str) -> dict:
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[-1].rsplit('```', 1)[0]
    return json.loads(text)


def _call_groq(req: PlanRequest, days_count: int) -> dict | None:
    key = os.getenv('GROQ_API_KEY')
    if not key:
        return None
    prompt = f'''Create a practical, clearly labelled DRAFT travel itinerary in JSON only. Do not claim live opening hours, availability, exact routes, or verified prices. If unsure, describe place types rather than inventing a named venue. Destination: {req.destination}. Dates: {req.start_date} to {req.end_date} ({days_count} days). Budget: {req.budget} {req.currency} total for {req.travelers} traveler(s). Interests: {', '.join(req.interests) or 'culture, food, sightseeing'}. Pace: {req.pace}. Style: {req.travel_style}. Return this schema: {{"summary":"string","budget_breakdown":{{"transport":number,"stay":number,"food":number,"activities":number,"buffer":number}},"days":[{{"date":"YYYY-MM-DD","title":"string","activities":[{{"time":"string","title":"string","description":"string","category":"sightseeing|food|transport|stay|experience","estimated_cost":number,"location":"string"}}]}}]}}. Include exactly {days_count} days and 3-4 activities per day. Keep estimated total within budget and say estimates are approximate.'''
    payload = {"model": os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile'), "messages": [{"role": "system", "content": "You are a careful travel-planning assistant. Never present uncertain information as verified fact. Return valid JSON only."}, {"role": "user", "content": prompt}], "temperature": 0.35, "response_format": {"type": "json_object"}}
    request = Request('https://api.groq.com/openai/v1/chat/completions', data=json.dumps(payload).encode(), headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}, method='POST')
    try:
        with urlopen(request, timeout=35) as response:
            body = json.loads(response.read().decode())
        return _safe_json(body['choices'][0]['message']['content'])
    except (HTTPError, URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError):
        return None


def _demo_plan(req: PlanRequest, count: int) -> dict:
    per_day = max(0, req.budget // count)
    ideas = [
        ('Arrival & orientation', [('Morning', 'Arrive and settle in', 'Leave room for check-in and rest; confirm your own transfer.' ,'transport'), ('Afternoon', 'Explore a nearby neighborhood', 'Choose a central area that matches your interests and check current access details.', 'sightseeing'), ('Evening', 'Local food discovery', 'Look for well-reviewed local dining nearby; confirm hours before going.', 'food')]),
        ('Culture & local highlights', [('Morning', 'Visit a major local landmark', 'Pick a currently open landmark or museum; check ticketing and visiting hours.', 'sightseeing'), ('Afternoon', 'Slow lunch and nearby walk', 'Keep the route flexible and allow time for breaks.', 'food'), ('Evening', 'Sunset or cultural experience', 'Choose a public viewpoint or a bookable local experience after checking availability.', 'experience')]),
        ('Nature, markets & a relaxed finish', [('Morning', 'Outdoor activity', 'Choose a park, waterfront, or nature spot appropriate to the destination and season.', 'experience'), ('Afternoon', 'Market or independent exploration', 'Browse a local market or a neighborhood you have not visited yet.', 'sightseeing'), ('Evening', 'Farewell meal and departure prep', 'Keep the last evening close to your stay and confirm departure logistics.', 'food')])]
    days=[]
    for i in range(count):
        title, activities = ideas[min(i,2)] if i < 3 else (f'Day {i+1}: Flexible exploration', [('Morning','Choose a priority attraction','Select a currently open place based on your interests.','sightseeing'),('Afternoon','Explore at your own pace','Leave time for food, rest, and changing plans.','experience'),('Evening','Dinner nearby','Check current reviews, hours, and transport options.','food')])
        d=req.start_date+timedelta(days=i)
        days.append({'date':d.isoformat(),'title':title,'activities':[{'time':t,'title':n,'description':desc,'category':cat,'estimated_cost':round(per_day*({'transport':.18,'sightseeing':.22,'food':.20,'experience':.15}.get(cat,.15))),'location':f'{req.destination} (suggestion; verify locally)'} for t,n,desc,cat in activities]})
    return {'summary': f'A flexible {count}-day starter plan for {req.destination}, tailored for {req.travelers} traveler(s), {req.pace.lower()} pace, and interests in {', '.join(req.interests) if req.interests else 'local highlights'}. This demo plan uses general suggestions, not verified live listings.', 'budget_breakdown': {'transport':round(req.budget*.2),'stay':round(req.budget*.35),'food':round(req.budget*.2),'activities':round(req.budget*.15),'buffer':req.budget-round(req.budget*.9)}, 'days':days}


def _validate_plan(plan: dict, req: PlanRequest, count: int) -> dict:
    if not isinstance(plan,dict):
        raise ValueError('AI response is not an object')
    days=plan.get('days')
    if not isinstance(days,list) or len(days) != count:
        raise ValueError('AI response has an unexpected number of days')
    allowed={'sightseeing','food','transport','stay','experience'}
    cleaned_days=[]
    for i, day in enumerate(days):
        if not isinstance(day,dict) or not isinstance(day.get('activities'),list) or not day['activities']:
            raise ValueError('AI response is missing activities')
        activities=[]
        for raw in day['activities'][:8]:
            if not isinstance(raw,dict) or not str(raw.get('title','')).strip():
                continue
            try: cost=max(0,int(float(raw.get('estimated_cost',0) or 0)))
            except (TypeError,ValueError): cost=0
            activities.append({'time':str(raw.get('time') or 'Flexible')[:40],'title':str(raw['title'])[:120],'description':str(raw.get('description') or 'Check current details before visiting.')[:400],'category':raw.get('category') if raw.get('category') in allowed else 'experience','estimated_cost':cost,'location':str(raw.get('location') or req.destination)[:120]})
        if not activities:
            raise ValueError('AI response has no usable activities')
        cleaned_days.append({'date':(req.start_date+timedelta(days=i)).isoformat(),'title':str(day.get('title') or f'Day {i+1}')[:100],'activities':activities})
    bd=plan.get('budget_breakdown') if isinstance(plan.get('budget_breakdown'),dict) else {}
    keys=['transport','stay','food','activities','buffer']
    cleaned={}
    for k in keys:
        try: cleaned[k]=max(0,int(float(bd.get(k,0) or 0)))
        except (TypeError,ValueError): cleaned[k]=0
    total=sum(cleaned.values())
    if total>req.budget and total:
        cleaned={k:int(v*req.budget/total) for k,v in cleaned.items()}
        cleaned['buffer']+=req.budget-sum(cleaned.values())
    plan['days']=cleaned_days
    plan['budget_breakdown']=cleaned
    plan['summary']=str(plan.get('summary') or f'A draft trip plan for {req.destination}. Verify details before booking.')[:1000]
    return plan

@app.get('/api/health')
def health():
    return {'status':'ok','ai_configured':bool(os.getenv('GROQ_API_KEY')),'storage':'supabase' if os.getenv('SUPABASE_URL') and os.getenv('SUPABASE_SERVICE_ROLE_KEY') else 'local SQLite'}

@app.get('/api/config')
def public_config():
    # Supabase URL + anon key are public client credentials. Never return server secrets here.
    return {'supabase_url':os.getenv('SUPABASE_URL',''),'supabase_anon_key':os.getenv('SUPABASE_ANON_KEY','')}

@app.post('/api/plan')
def create_plan(req: PlanRequest):
    count=(req.end_date-req.start_date).days+1
    if count > 14:
        raise HTTPException(status_code=422, detail='Please choose a trip of 14 days or fewer.')
    plan=_call_groq(req,count)
    source='groq'
    if plan is None:
        plan=_demo_plan(req,count); source='demo'
    try:
        plan=_validate_plan(plan,req,count)
    except (ValueError, TypeError, AttributeError):
        plan=_demo_plan(req,count); source='demo'
    return {'id':str(uuid.uuid4()),'destination':req.destination,'start_date':req.start_date.isoformat(),'end_date':req.end_date.isoformat(),'budget':req.budget,'currency':req.currency,'travelers':req.travelers,'pace':req.pace,'interests':req.interests,'travel_style':req.travel_style,'summary':plan['summary'],'budget_breakdown':plan['budget_breakdown'],'days':plan['days'],'ai_mode':source,'created_at':date.today().isoformat()}

def _supabase_user(authorization: str | None):
    if not authorization or not authorization.lower().startswith('bearer '):
        return None
    url=os.getenv('SUPABASE_URL'); anon=os.getenv('SUPABASE_ANON_KEY')
    if not url or not anon:
        return None
    try:
        from supabase import create_client
        client=create_client(url,anon)
        result=client.auth.get_user(authorization.split(' ',1)[1])
        return result.user.id if result and result.user else None
    except Exception:
        return None

@app.get('/api/trips')
def list_trips(authorization: str | None = Header(default=None), workspace_id: str | None = Header(default=None, alias='X-Workspace-Id')):
    user_id=_supabase_user(authorization)
    url=os.getenv('SUPABASE_URL'); service=os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    if user_id and url and service:
        try:
            from supabase import create_client
            client=create_client(url,service)
            rows=client.table('trips').select('payload').eq('owner_id',user_id).order('created_at',desc=True).limit(50).execute().data
            return [row['payload'] for row in rows]
        except Exception:
            pass
    if not workspace_id:
        return []
    conn=_db()
    try:
        rows=conn.execute('SELECT payload FROM trips WHERE workspace_id=? ORDER BY created_at DESC LIMIT 50',(workspace_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]
    finally: conn.close()

@app.post('/api/trips')
def save_trip(body: SaveRequest, authorization: str | None = Header(default=None), workspace_id: str | None = Header(default=None, alias='X-Workspace-Id')):
    trip=body.trip
    if not isinstance(trip.get('destination'),str) or not trip.get('destination'):
        raise HTTPException(status_code=422,detail='Trip destination is required.')
    trip.setdefault('id',str(uuid.uuid4()))
    # Cloud writes require a verified Supabase user; otherwise use the local demo DB.
    user_id=_supabase_user(authorization)
    url=os.getenv('SUPABASE_URL'); service=os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    if user_id and url and service:
        try:
            from supabase import create_client
            client=create_client(url,service)
            client.table('trips').upsert({'id':trip['id'],'owner_id':user_id,'destination':trip['destination'],'payload':trip}).execute()
            return {'saved':True,'storage':'supabase','trip':trip}
        except Exception:
            pass
    if not workspace_id:
        raise HTTPException(status_code=400,detail='Workspace identifier is missing; refresh the app and try again.')
    conn=_db()
    try:
        conn.execute('INSERT OR REPLACE INTO trips (id,destination,payload,workspace_id) VALUES (?,?,?,?)',(trip['id'],trip['destination'],json.dumps(trip),workspace_id))
        conn.commit()
    finally: conn.close()
    return {'saved':True,'storage':'local','trip':trip}

@app.get('/api/photo')
def photo(query: str='travel destination'):
    key=os.getenv('UNSPLASH_ACCESS_KEY')
    if not key: return {'url':None,'source':'fallback'}
    request=Request('https://api.unsplash.com/search/photos?query='+__import__('urllib.parse').parse.quote(query)+'&per_page=1&orientation=landscape',headers={'Authorization':f'Client-ID {key}'})
    try:
        with urlopen(request,timeout=8) as response: data=json.loads(response.read().decode())
        photo=data.get('results',[{}])[0]
        return {'url':photo.get('urls',{}).get('regular'),'alt':photo.get('alt_description') or query,'source':'unsplash'}
    except Exception: return {'url':None,'source':'fallback'}

# In production, the Docker image serves the built React SPA from the same origin.
WEB_DIST=BASE.parent/'dist'
if (WEB_DIST/'assets').is_dir():
    app.mount('/assets', StaticFiles(directory=WEB_DIST/'assets'), name='frontend-assets')

@app.get('/', include_in_schema=False)
def frontend_index():
    index=WEB_DIST/'index.html'
    if index.is_file(): return FileResponse(index)
    return {'message':'Wanderwise API is running. Start the Vite frontend in development.'}

@app.get('/{path:path}', include_in_schema=False)
def frontend_fallback(path: str):
    if path.startswith('api/'):
        raise HTTPException(status_code=404,detail='API endpoint not found.')
    index=WEB_DIST/'index.html'
    if index.is_file(): return FileResponse(index)
    raise HTTPException(status_code=404,detail='Page not found.')
