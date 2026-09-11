from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import tailor_routes, reformat_routes, template_preview_routes, resumes_routes, jd_routes

app = FastAPI(title="Auto Resume Tailor")

# CORS middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Local development
        "https://ai-powered-resume-builder-egn6vytdc-manas-s-projects-97f76173.vercel.app",  # Vercel production
        "https://refactrapp.com",
        "https://www.refactrapp.com",
    ],
    allow_origin_regex=r"(https://.*\.vercel\.app|chrome-extension://.*)",  # Vercel deployments + the refactr Chrome extension
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(tailor_routes.router, prefix="/api")
app.include_router(reformat_routes.router, prefix="/api")
app.include_router(template_preview_routes.router, prefix="/api")
app.include_router(resumes_routes.router, prefix="/api")
app.include_router(jd_routes.router, prefix="/api")

@app.get("/")
def root():
    return {
        "message": "Auto Resume Tailor API",
        "status": "running",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "api": "/api"
        }
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}
