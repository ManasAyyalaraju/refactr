"""
Domain-specific prompt templates for resume tailoring.
Each domain has detailed guidance for emphasis, language patterns, metrics, and skill priorities.
"""

DOMAIN_PROMPTS = {
    "Technology": {
        "Software Engineering (SWE)": {
            "emphasis": [
                "Backend logic, APIs, and scalable components",
                "System architecture and design patterns",
                "Performance optimization and debugging",
                "Code quality, testing, and version control",
                "Collaboration with cross-functional teams",
                "Technical problem-solving and innovation"
            ],
            "language_patterns": [
                "developed", "implemented", "architected", "designed",
                "optimized", "debugged", "refactored", "deployed",
                "built scalable systems", "improved performance",
                "reduced latency", "increased throughput"
            ],
            "metrics": [
                "Performance improvements (latency, throughput)",
                "Code quality metrics (test coverage, bug reduction)",
                "System scalability (users, requests handled)",
                "Development velocity (features shipped, time saved)"
            ],
            "skill_priorities": {
                "high": ["Programming languages", "Frameworks", "Version control", "Testing"],
                "medium": ["Cloud platforms", "Databases", "CI/CD"],
                "low": ["Frontend frameworks (unless full-stack)", "Design tools"]
            },
            "terminology": [
                "APIs", "microservices", "scalability", "performance",
                "code review", "agile", "scrum", "CI/CD", "deployment"
            ]
        },
        
        "Data Analyst / Business Intelligence": {
            "emphasis": [
                "SQL querying and data extraction",
                "Data cleaning, validation, and quality assurance",
                "KPIs, dashboards, and visualization",
                "Business insights and storytelling",
                "Stakeholder communication and reporting",
                "EDA, trend analysis, and anomaly detection"
            ],
            "language_patterns": [
                "analyzed", "validated", "cleaned", "evaluated",
                "built dashboards", "constructed KPIs",
                "generated insights that informed decisions",
                "translated business questions into analytical findings",
                "identified trends and patterns",
                "presented findings to stakeholders"
            ],
            "metrics": [
                "Query performance improvements",
                "Dashboard adoption rates",
                "Time saved through automation",
                "Data accuracy improvements",
                "Business impact (revenue, cost savings, efficiency)"
            ],
            "skill_priorities": {
                "high": ["SQL", "Python", "Pandas", "Tableau", "Power BI", "Excel"],
                "medium": ["NumPy", "Matplotlib", "Seaborn", "Jupyter"],
                "low": ["Frontend technologies", "System administration", "Low-level programming"]
            },
            "terminology": [
                "KPIs", "metrics", "dashboards", "data pipelines",
                "ETL", "data validation", "stakeholder reporting", "EDA"
            ]
        },
        
        "Machine Learning / AI / Data Science": {
            "emphasis": [
                "Model development and evaluation",
                "Feature engineering and preprocessing",
                "Experimentation and iteration",
                "Model performance metrics (ROC-AUC, precision, recall)",
                "Data pipeline development",
                "Production deployment and inference"
            ],
            "language_patterns": [
                "developed models", "engineered features",
                "achieved X% accuracy", "improved model performance",
                "built end-to-end ML pipelines", "deployed models to production",
                "reduced false positives by X%", "optimized hyperparameters"
            ],
            "metrics": [
                "Model performance (accuracy, ROC-AUC, precision, recall)",
                "Feature importance and impact",
                "Training time and inference latency",
                "Business impact (revenue, cost savings, efficiency)"
            ],
            "skill_priorities": {
                "high": ["Python", "scikit-learn", "Pandas", "NumPy", "XGBoost", "TensorFlow", "PyTorch"],
                "medium": ["SQL", "Jupyter", "MLflow", "FastAPI"],
                "low": ["Frontend technologies (unless relevant)", "System administration"]
            },
            "terminology": [
                "feature engineering", "model training", "cross-validation",
                "hyperparameter tuning", "ROC-AUC", "precision", "recall",
                "inference", "deployment", "MLOps"
            ]
        },
        
        "Analytics Engineer / Data Engineering": {
            "emphasis": [
                "Data transformation and ETL pipelines",
                "Structured datasets and data modeling",
                "Data quality checks and validation",
                "Reproducible workflows and documentation",
                "Metric definitions and data governance",
                "End-to-end data flows"
            ],
            "language_patterns": [
                "built transformation steps", "structured datasets",
                "validated data quality", "created clean analytical tables",
                "documented data logic for reproducibility",
                "optimized data pipelines", "ensured data consistency"
            ],
            "metrics": [
                "Pipeline performance (processing time, throughput)",
                "Data quality improvements (accuracy, completeness)",
                "Time saved through automation",
                "Reduced data errors or inconsistencies"
            ],
            "skill_priorities": {
                "high": ["SQL", "Python", "Pandas", "ETL tools", "Data modeling"],
                "medium": ["Airflow", "dbt", "Spark", "Cloud platforms"],
                "low": ["Frontend technologies", "Visualization tools (unless relevant)"]
            },
            "terminology": [
                "ETL", "data pipelines", "data modeling", "data quality",
                "data governance", "dimensional modeling", "star schema"
            ]
        },
        
        "Cloud / DevOps": {
            "emphasis": [
                "Infrastructure automation and deployment",
                "CI/CD pipelines and workflows",
                "Monitoring, logging, and observability",
                "Container orchestration and scalability",
                "Security and compliance",
                "System reliability and uptime"
            ],
            "language_patterns": [
                "automated deployments", "built CI/CD pipelines",
                "improved system reliability", "reduced deployment time",
                "implemented monitoring solutions", "optimized infrastructure costs"
            ],
            "metrics": [
                "Deployment frequency and time",
                "System uptime and reliability",
                "Infrastructure cost savings",
                "Incident reduction"
            ],
            "skill_priorities": {
                "high": ["Cloud platforms (AWS, GCP, Azure)", "Docker", "Kubernetes", "CI/CD tools"],
                "medium": ["Terraform", "Ansible", "Monitoring tools"],
                "low": ["Application development languages (unless relevant)"]
            },
            "terminology": [
                "CI/CD", "infrastructure as code", "containerization",
                "orchestration", "monitoring", "observability", "SRE"
            ]
        }
    },
    
    "Finance": {
        "Commercial Banking": {
            "emphasis": [
                "Client relationship management",
                "Loan origination and underwriting",
                "Credit analysis and risk assessment",
                "Regulatory compliance",
                "Portfolio management",
                "Customer service and satisfaction"
            ],
            "language_patterns": [
                "managed client relationships", "analyzed creditworthiness",
                "originated loans", "ensured regulatory compliance",
                "improved customer satisfaction", "reduced risk exposure"
            ],
            "metrics": [
                "Loan volume ($)",
                "Client acquisition and retention",
                "Portfolio performance",
                "Risk reduction",
                "Customer satisfaction scores"
            ],
            "skill_priorities": {
                "high": ["Financial analysis", "Credit risk", "Regulatory knowledge", "CRM systems"],
                "medium": ["Excel", "Financial modeling", "SQL"],
                "low": ["Progra)mming languages (unless relevant", "Design tools"]
            },
            "terminology": [
                "underwriting", "credit analysis", "loan origination",
                "regulatory compliance", "portfolio management", "KYC"
            ]
        },
        
        "Investment Banking": {
            "emphasis": [
                "Financial modeling and valuation",
                "Deal execution and transaction support",
                "Client relationship management",
                "Market research and due diligence",
                "Regulatory compliance",
                "Pitch book preparation"
            ],
            "language_patterns": [
                "executed transactions", "performed due diligence",
                "built financial models", "analyzed market trends",
                "supported M&A transactions", "prepared pitch materials",
                "valued companies", "structured deals"
            ],
            "metrics": [
                "Deal value ($)",
                "Transaction volume",
                "Client acquisition",
                "Revenue generation",
                "Time to close"
            ],
            "skill_priorities": {
                "high": ["Excel", "Financial Modeling", "Valuation", "Bloomberg", "PowerPoint"],
                "medium": ["Python", "SQL", "Market research tools"],
                "low": ["Web development", "Design tools"]
            },
            "terminology": [
                "DCF", "LBO", "M&A", "IPO", "due diligence",
                "pitch book", "comparable company analysis", "precedent transactions"
            ]
        }
    },
    
    "Healthcare": {
        "Clinical (Nursing, Physician, etc.)": {
            "emphasis": [
                "Patient care and outcomes",
                "Clinical protocols and best practices",
                "Compliance and regulatory adherence",
                "Interdisciplinary collaboration",
                "Documentation and record-keeping",
                "Quality improvement initiatives"
            ],
            "language_patterns": [
                "managed patient care", "ensured compliance",
                "improved patient outcomes", "maintained clinical standards",
                "collaborated with healthcare team", "implemented quality improvements"
            ],
            "metrics": [
                "Patient outcomes (recovery rates, satisfaction)",
                "Compliance rates",
                "Quality metrics",
                "Patient safety improvements"
            ],
            "skill_priorities": {
                "high": ["Clinical skills", "Medical knowledge", "EMR systems", "Certifications"],
                "medium": ["Communication", "Documentation", "Regulatory knowledge"],
                "low": ["Technical programming", "Business tools"]
            },
            "terminology": [
                "patient care", "clinical protocols", "HIPAA", "EMR",
                "quality improvement", "evidence-based practice"
            ]
        }
    },
    
    "Marketing": {
        "Digital Marketing": {
            "emphasis": [
                "Campaign development and execution",
                "Digital analytics and performance tracking",
                "SEO/SEM and content optimization",
                "Social media management",
                "Conversion optimization",
                "ROI and performance metrics"
            ],
            "language_patterns": [
                "launched campaigns", "increased engagement",
                "improved conversion rates", "optimized ad performance",
                "drove traffic", "generated leads"
            ],
            "metrics": [
                "Campaign performance (CTR, conversion rates)",
                "Traffic and engagement",
                "ROI and revenue attribution",
                "Lead generation"
            ],
            "skill_priorities": {
                "high": ["Marketing platforms", "Analytics tools", "SEO/SEM", "Content creation"],
                "medium": ["Social media tools", "Email marketing", "A/B testing"],
                "low": ["Technical programming (unless relevant)", "Design tools (unless creative role)"]
            },
            "terminology": [
                "CTR", "conversion rate", "ROI", "SEO", "SEM",
                "A/B testing", "funnel optimization", "attribution"
            ]
        }
    }
}


def get_domain_prompt(industry: str, sub_domain: str) -> dict:
    """
    Get domain-specific prompt configuration.

    Args:
        industry: Detected industry (e.g., "Technology")
        sub_domain: Detected sub-domain (e.g., "Data Analyst")

    Returns:
        Domain-specific prompt config, or None if not found
    """
    return DOMAIN_PROMPTS.get(industry, {}).get(sub_domain, None)


def format_domain_guidance(entry: dict) -> str:
    """
    Condense a domain_prompts entry into one short, fixed-size briefing line
    instead of dumping its full emphasis/language_patterns/metrics/
    skill_priorities/terminology lists into the tailoring prompt.

    That full-dump approach was tried before and reverted: it added a few
    hundred tokens on top of an already-dense prompt and gave the model more
    instructions to juggle alongside the compression/expansion rules, which
    measurably slowed generation. This keeps the injected guidance to a
    handful of terms (~40-60 tokens) regardless of how much data a given
    domain entry has, so it can't reproduce that regression.
    """
    top_emphasis = entry.get("emphasis", [])[:2]
    top_terms = entry.get("terminology", [])[:5]
    top_skills = entry.get("skill_priorities", {}).get("high", [])[:4]

    parts = []
    if top_emphasis:
        parts.append(f"Emphasize: {', '.join(top_emphasis)}.")
    if top_terms:
        parts.append(f"Use terminology like: {', '.join(top_terms)}.")
    if top_skills:
        parts.append(f"Prioritize these skills if present: {', '.join(top_skills)}.")

    return " ".join(parts)

