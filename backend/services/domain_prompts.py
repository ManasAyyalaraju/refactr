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
        },

        "Frontend Development": {
            "emphasis": [
                "UI implementation and component architecture",
                "Responsive design and cross-browser compatibility",
                "Client-side performance and accessibility",
                "State management",
                "Collaboration with design and product teams",
                "Visual polish and user experience"
            ],
            "language_patterns": [
                "built UI components", "implemented responsive layouts",
                "optimized bundle size", "improved page load time",
                "ensured accessibility (WCAG) compliance",
                "translated designs into working interfaces",
                "reduced render time", "collaborated with designers"
            ],
            "metrics": [
                "Page load / performance improvements (Core Web Vitals)",
                "Accessibility compliance improvements",
                "Bundle size reduction",
                "User engagement or conversion improvements"
            ],
            "skill_priorities": {
                "high": ["JavaScript/TypeScript", "React/Vue/Angular", "HTML/CSS", "State management (Redux, Context)"],
                "medium": ["Testing (Jest, Cypress)", "Build tools (Webpack, Vite)", "Accessibility tools"],
                "low": ["Backend languages (unless full-stack)", "Database administration"]
            },
            "terminology": [
                "component-based architecture", "responsive design", "accessibility (a11y)",
                "Core Web Vitals", "state management", "client-side rendering",
                "SSR/CSR", "cross-browser compatibility"
            ]
        },

        "Backend Development": {
            "emphasis": [
                "API design and server-side logic",
                "Database design and query optimization",
                "System reliability and scalability",
                "Authentication, authorization, and security",
                "Service architecture",
                "Performance under load"
            ],
            "language_patterns": [
                "designed APIs", "built backend services", "optimized queries",
                "implemented authentication", "scaled infrastructure",
                "reduced response times", "improved system reliability",
                "architected data models"
            ],
            "metrics": [
                "API response time / latency",
                "System uptime and reliability",
                "Query performance improvements",
                "Requests or throughput handled"
            ],
            "skill_priorities": {
                "high": ["Server-side languages (Python, Java, Node.js, Go)", "Databases (SQL/NoSQL)", "API design (REST/GraphQL)"],
                "medium": ["Caching (Redis)", "Message queues", "Cloud platforms"],
                "low": ["Frontend frameworks (unless full-stack)", "Design tools"]
            },
            "terminology": [
                "REST/GraphQL APIs", "microservices", "database indexing",
                "caching", "authentication/authorization", "load balancing",
                "horizontal scaling", "service-oriented architecture"
            ]
        },

        "Full-Stack Development": {
            "emphasis": [
                "End-to-end feature ownership (frontend + backend)",
                "API design and client integration",
                "Database schema design",
                "Deployment and basic DevOps",
                "Cross-functional collaboration",
                "Balancing UX with system performance"
            ],
            "language_patterns": [
                "built end-to-end features", "designed and implemented APIs",
                "integrated frontend with backend services", "deployed applications",
                "owned features from design to production", "collaborated across the stack"
            ],
            "metrics": [
                "Feature delivery velocity",
                "End-to-end performance improvements",
                "User-facing metrics (engagement, conversion)",
                "System reliability"
            ],
            "skill_priorities": {
                "high": ["JavaScript/TypeScript", "A frontend framework (React/Vue)", "A backend language/framework (Node.js, Python, Java)", "Databases"],
                "medium": ["Cloud platforms", "CI/CD", "API design"],
                "low": ["Highly specialized infra tools (unless relevant)"]
            },
            "terminology": [
                "full-stack", "end-to-end ownership", "REST APIs",
                "client-server architecture", "deployment pipelines", "monorepo", "MVC"
            ]
        },

        "Mobile Development": {
            "emphasis": [
                "Native or cross-platform app development",
                "Mobile UX and performance",
                "Platform-specific guidelines (iOS/Android)",
                "App store release process",
                "Offline support and device APIs",
                "Crash-free stability"
            ],
            "language_patterns": [
                "built and shipped mobile apps", "optimized app performance",
                "implemented native features", "integrated device APIs",
                "reduced crash rate", "released to App Store/Play Store",
                "improved app responsiveness"
            ],
            "metrics": [
                "App store ratings",
                "Crash-free session rate",
                "App load / startup time",
                "User retention (DAU/MAU)"
            ],
            "skill_priorities": {
                "high": ["Swift/Kotlin", "React Native/Flutter", "Mobile UI frameworks", "App store deployment"],
                "medium": ["Push notifications", "Offline storage", "Device APIs"],
                "low": ["Backend/server-side development (unless full-stack)"]
            },
            "terminology": [
                "native development", "cross-platform", "App Store/Play Store",
                "push notifications", "mobile UX", "offline-first", "crash reporting"
            ]
        },

        "QA / Testing": {
            "emphasis": [
                "Test planning and coverage",
                "Manual and automated testing",
                "Bug identification and triage",
                "Regression testing",
                "Quality processes and CI integration",
                "Collaboration with engineering"
            ],
            "language_patterns": [
                "wrote test plans", "automated test suites",
                "identified and triaged bugs", "improved test coverage",
                "reduced regression issues", "integrated tests into CI/CD",
                "ensured release quality"
            ],
            "metrics": [
                "Test coverage percentage",
                "Bugs found pre-release vs. post-release",
                "Regression rate reduction",
                "Release cycle time"
            ],
            "skill_priorities": {
                "high": ["Test automation frameworks (Selenium, Cypress, Playwright)", "Manual testing methodology", "Bug tracking tools (Jira)"],
                "medium": ["SQL", "Basic scripting (Python/JavaScript)", "CI/CD integration"],
                "low": ["Full application development", "Infrastructure management"]
            },
            "terminology": [
                "test cases", "regression testing", "test automation",
                "QA processes", "bug triage", "CI/CD integration", "test coverage", "UAT"
            ]
        },

        "UX/UI / Product Design": {
            "emphasis": [
                "User research and usability testing",
                "Interaction and visual design, prototyping",
                "Design systems and component libraries",
                "Cross-functional collaboration with engineering/PM",
                "Accessibility-first design",
                "Design-to-development handoff"
            ],
            "language_patterns": [
                "conducted user research", "designed wireframes and prototypes",
                "built design systems", "collaborated with engineers on implementation",
                "improved usability", "conducted usability testing",
                "translated user needs into interfaces"
            ],
            "metrics": [
                "Usability / user satisfaction scores",
                "Design adoption rate",
                "Conversion or engagement improvements from redesigns",
                "Design system component reuse"
            ],
            "skill_priorities": {
                "high": ["Figma", "Prototyping", "User research", "Wireframing"],
                "medium": ["Design systems", "HTML/CSS basics", "Usability testing tools"],
                "low": ["Backend development", "Advanced programming languages"]
            },
            "terminology": [
                "user research", "wireframes", "prototyping", "design systems",
                "usability testing", "interaction design", "accessibility (a11y)", "design handoff"
            ]
        },

        "Forward Deployed Engineering": {
            "emphasis": [
                "On-site or embedded client implementation",
                "Rapid custom solution building",
                "Cross-functional client collaboration",
                "Technical problem-solving under ambiguity",
                "Product customization and configuration",
                "Client relationship and requirements translation"
            ],
            "language_patterns": [
                "deployed solutions directly with clients", "built custom integrations",
                "rapidly prototyped solutions for client needs",
                "translated client requirements into technical implementations",
                "resolved production issues on-site", "partnered with client engineering teams"
            ],
            "metrics": [
                "Client deployment success rate",
                "Time to deployment / implementation",
                "Client satisfaction",
                "Issues resolved on-site"
            ],
            "skill_priorities": {
                "high": ["Programming languages (Python, Java, etc.)", "APIs & integrations", "Problem-solving under ambiguity", "Client-facing communication"],
                "medium": ["Cloud platforms", "Databases", "Scripting"],
                "low": ["Deep specialization in one narrow stack"]
            },
            "terminology": [
                "forward deployed", "client-embedded engineering", "custom integrations",
                "rapid prototyping", "solution deployment", "client requirements"
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
                "low": ["Programming languages (unless relevant)", "Design tools"]
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
        },

        "Corporate Finance": {
            "emphasis": [
                "Financial planning and analysis (FP&A)",
                "Budgeting and forecasting",
                "Capital allocation decisions",
                "Financial reporting",
                "Cross-departmental collaboration",
                "Cost management"
            ],
            "language_patterns": [
                "managed budgets", "built financial forecasts", "analyzed variance",
                "supported capital allocation decisions", "prepared financial reports",
                "partnered with business units", "identified cost savings"
            ],
            "metrics": [
                "Budget accuracy / variance",
                "Cost savings identified",
                "Forecast accuracy",
                "Revenue or margin impact"
            ],
            "skill_priorities": {
                "high": ["Excel", "Financial modeling", "Budgeting/forecasting tools", "Financial reporting"],
                "medium": ["SQL", "ERP systems (SAP, Oracle)", "PowerPoint"],
                "low": ["Programming languages (unless relevant)", "Design tools"]
            },
            "terminology": [
                "FP&A", "budgeting", "forecasting", "variance analysis",
                "capital allocation", "financial reporting", "cost management"
            ]
        },

        "Risk Management": {
            "emphasis": [
                "Risk identification and assessment",
                "Quantitative risk modeling",
                "Regulatory compliance",
                "Risk mitigation strategy",
                "Reporting to stakeholders",
                "Market, credit, or operational risk analysis"
            ],
            "language_patterns": [
                "assessed risk exposure", "built risk models",
                "ensured regulatory compliance", "developed mitigation strategies",
                "monitored risk metrics", "reported findings to leadership",
                "reduced risk exposure"
            ],
            "metrics": [
                "Risk exposure reduction",
                "Compliance rate",
                "Model accuracy",
                "Losses avoided or mitigated"
            ],
            "skill_priorities": {
                "high": ["Risk modeling", "Excel", "Statistical analysis", "Regulatory frameworks"],
                "medium": ["Python/R", "SQL", "VaR / stress testing tools"],
                "low": ["Frontend/web development", "Design tools"]
            },
            "terminology": [
                "value at risk (VaR)", "stress testing", "credit risk",
                "market risk", "operational risk", "regulatory compliance", "risk mitigation"
            ]
        },

        "Financial Analysis": {
            "emphasis": [
                "Financial statement analysis",
                "Valuation and modeling",
                "Trend and variance analysis",
                "Investment or business recommendations",
                "Reporting and presentation",
                "Data-driven decision support"
            ],
            "language_patterns": [
                "analyzed financial statements", "built valuation models",
                "identified trends", "presented recommendations",
                "supported investment decisions", "conducted variance analysis"
            ],
            "metrics": [
                "Forecast / model accuracy",
                "Cost savings or revenue impact identified",
                "Analysis turnaround time",
                "Recommendation adoption rate"
            ],
            "skill_priorities": {
                "high": ["Excel", "Financial modeling", "Valuation methods", "Financial statement analysis"],
                "medium": ["SQL", "Python/R", "PowerPoint", "Bloomberg"],
                "low": ["Web/software development", "Design tools"]
            },
            "terminology": [
                "financial modeling", "valuation", "DCF", "variance analysis",
                "financial statements", "trend analysis"
            ]
        },

        "Accounting": {
            "emphasis": [
                "Financial record-keeping and reconciliation",
                "GAAP and regulatory compliance",
                "Month-end and year-end close",
                "Accounts payable/receivable",
                "Audit support",
                "Accuracy and attention to detail"
            ],
            "language_patterns": [
                "reconciled accounts", "ensured GAAP compliance",
                "managed month-end close", "processed accounts payable/receivable",
                "supported audits", "maintained accurate financial records",
                "identified discrepancies"
            ],
            "metrics": [
                "Close cycle time",
                "Reconciliation accuracy",
                "Audit findings reduced",
                "Error or discrepancy rate"
            ],
            "skill_priorities": {
                "high": ["Excel", "Accounting software (QuickBooks, NetSuite, SAP)", "GAAP knowledge"],
                "medium": ["ERP systems", "Financial reporting"],
                "low": ["Programming languages", "Design tools"]
            },
            "terminology": [
                "GAAP", "reconciliation", "accounts payable/receivable",
                "month-end close", "general ledger", "audit", "journal entries"
            ]
        },

        "Wealth Management": {
            "emphasis": [
                "Client relationship management",
                "Investment portfolio strategy",
                "Financial planning and advisory",
                "Regulatory compliance",
                "Client acquisition and retention",
                "Personalized financial guidance"
            ],
            "language_patterns": [
                "managed client portfolios", "developed financial plans",
                "advised clients on investment strategy", "ensured compliance",
                "grew assets under management", "built client relationships"
            ],
            "metrics": [
                "Assets under management (AUM) growth",
                "Client retention / acquisition",
                "Portfolio performance",
                "Client satisfaction"
            ],
            "skill_priorities": {
                "high": ["Financial planning", "Portfolio management", "Client relationship management", "Regulatory knowledge (Series 7/65)"],
                "medium": ["Excel", "CRM systems", "Financial modeling"],
                "low": ["Programming languages", "Design tools"]
            },
            "terminology": [
                "assets under management (AUM)", "portfolio management",
                "financial planning", "wealth advisory", "asset allocation", "fiduciary"
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
        },

        "Healthcare Administration": {
            "emphasis": [
                "Operations management within healthcare settings",
                "Regulatory and compliance oversight",
                "Budget and resource management",
                "Staff coordination",
                "Patient experience improvement",
                "Process improvement"
            ],
            "language_patterns": [
                "managed healthcare operations", "ensured regulatory compliance",
                "coordinated staff and resources", "improved patient experience",
                "managed budgets", "implemented process improvements"
            ],
            "metrics": [
                "Operational efficiency improvements",
                "Compliance rate",
                "Patient satisfaction scores",
                "Cost savings"
            ],
            "skill_priorities": {
                "high": ["Healthcare regulations (HIPAA)", "EMR/EHR systems", "Operations management"],
                "medium": ["Excel", "Budgeting", "Staff scheduling systems"],
                "low": ["Clinical/technical programming skills"]
            },
            "terminology": [
                "HIPAA", "EMR/EHR", "healthcare compliance", "patient experience",
                "operations management", "credentialing"
            ]
        },

        "Medical Research": {
            "emphasis": [
                "Study design and protocol development",
                "Data collection and analysis",
                "Regulatory and IRB compliance",
                "Literature review",
                "Grant writing and funding",
                "Scientific communication"
            ],
            "language_patterns": [
                "designed research studies", "collected and analyzed data",
                "ensured IRB/regulatory compliance", "conducted literature reviews",
                "authored publications", "presented findings", "supported grant applications"
            ],
            "metrics": [
                "Publications / presentations produced",
                "Grant funding secured",
                "Sample size / study enrollment",
                "Data accuracy"
            ],
            "skill_priorities": {
                "high": ["Statistical analysis (R, SPSS, SAS)", "Research methodology", "Data collection tools"],
                "medium": ["Python", "Literature databases (PubMed)", "Grant writing"],
                "low": ["Software engineering", "Design tools"]
            },
            "terminology": [
                "IRB approval", "clinical trials", "statistical significance",
                "literature review", "peer review", "grant funding", "study protocol"
            ]
        },

        "Public Health": {
            "emphasis": [
                "Community health assessment",
                "Program design and implementation",
                "Epidemiological data analysis",
                "Policy and advocacy",
                "Health education and outreach",
                "Stakeholder collaboration"
            ],
            "language_patterns": [
                "designed public health programs", "analyzed epidemiological data",
                "conducted community health assessments", "developed health education materials",
                "collaborated with stakeholders", "advocated for policy change"
            ],
            "metrics": [
                "Program reach / enrollment",
                "Health outcome improvements",
                "Community engagement",
                "Funding secured"
            ],
            "skill_priorities": {
                "high": ["Epidemiology", "Statistical analysis", "Program evaluation", "Public health data systems"],
                "medium": ["Excel", "R/Python", "Survey design"],
                "low": ["Software engineering", "Clinical skills"]
            },
            "terminology": [
                "epidemiology", "community health", "health disparities",
                "program evaluation", "public health policy", "health outcomes"
            ]
        },

        "Healthcare IT": {
            "emphasis": [
                "EHR/EMR system implementation and support",
                "Healthcare data interoperability",
                "HIPAA-compliant systems",
                "IT infrastructure for clinical workflows",
                "Systems integration",
                "User support and training"
            ],
            "language_patterns": [
                "implemented EHR/EMR systems", "ensured HIPAA compliance",
                "integrated healthcare data systems", "supported clinical IT infrastructure",
                "trained staff on systems", "resolved technical issues"
            ],
            "metrics": [
                "System uptime",
                "User adoption rate",
                "Data accuracy / interoperability improvements",
                "Support ticket resolution time"
            ],
            "skill_priorities": {
                "high": ["EHR/EMR systems (Epic, Cerner)", "HL7/FHIR standards", "HIPAA compliance"],
                "medium": ["SQL", "IT support", "Systems integration"],
                "low": ["Frontend web development", "Design tools"]
            },
            "terminology": [
                "EHR/EMR", "HL7/FHIR", "HIPAA", "interoperability",
                "healthcare data standards", "clinical workflows"
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
        },

        "Content Marketing": {
            "emphasis": [
                "Content strategy and editorial planning",
                "Storytelling and brand voice",
                "SEO-driven content creation",
                "Content performance analysis",
                "Cross-channel distribution",
                "Audience engagement"
            ],
            "language_patterns": [
                "developed content strategy", "wrote and published content",
                "optimized for SEO", "grew audience engagement",
                "analyzed content performance", "managed editorial calendar"
            ],
            "metrics": [
                "Organic traffic growth",
                "Engagement rate",
                "Content production volume",
                "Conversion from content"
            ],
            "skill_priorities": {
                "high": ["Content strategy", "SEO", "Copywriting", "CMS platforms (WordPress)"],
                "medium": ["Analytics tools (Google Analytics)", "Social media tools", "Email marketing"],
                "low": ["Technical programming", "Paid advertising platforms"]
            },
            "terminology": [
                "SEO", "content strategy", "editorial calendar", "organic traffic",
                "content marketing funnel", "brand voice"
            ]
        },

        "Brand Management": {
            "emphasis": [
                "Brand strategy and positioning",
                "Campaign development",
                "Cross-functional brand consistency",
                "Market research and consumer insights",
                "Creative direction",
                "Brand performance tracking"
            ],
            "language_patterns": [
                "developed brand strategy", "launched campaigns",
                "ensured brand consistency", "conducted market research",
                "partnered with creative teams", "tracked brand performance"
            ],
            "metrics": [
                "Brand awareness / perception metrics",
                "Campaign performance",
                "Market share",
                "Consumer engagement"
            ],
            "skill_priorities": {
                "high": ["Brand strategy", "Market research", "Campaign management", "Consumer insights"],
                "medium": ["Analytics tools", "Adobe Creative Suite", "Project management tools"],
                "low": ["Technical programming", "SEO/SEM"]
            },
            "terminology": [
                "brand positioning", "brand equity", "market research",
                "consumer insights", "campaign strategy", "brand guidelines"
            ]
        },

        "Marketing Analytics": {
            "emphasis": [
                "Marketing performance measurement",
                "Data-driven campaign optimization",
                "Attribution modeling",
                "Dashboards and reporting",
                "A/B testing",
                "ROI analysis"
            ],
            "language_patterns": [
                "analyzed campaign performance", "built marketing dashboards",
                "conducted A/B tests", "optimized ad spend",
                "measured ROI", "built attribution models"
            ],
            "metrics": [
                "Campaign ROI",
                "Conversion rate improvements",
                "Attribution accuracy",
                "Cost per acquisition (CPA)"
            ],
            "skill_priorities": {
                "high": ["SQL", "Excel", "Analytics tools (Google Analytics, Mixpanel)", "A/B testing"],
                "medium": ["Python/R", "Tableau/Power BI", "Attribution modeling"],
                "low": ["Design tools", "Content creation"]
            },
            "terminology": [
                "attribution modeling", "ROI", "conversion rate", "CPA",
                "A/B testing", "marketing dashboards", "funnel analysis"
            ]
        },

        "Product Marketing": {
            "emphasis": [
                "Go-to-market strategy",
                "Positioning and messaging",
                "Competitive analysis",
                "Cross-functional launch coordination",
                "Sales enablement",
                "Customer and market insights"
            ],
            "language_patterns": [
                "developed go-to-market strategy", "crafted positioning and messaging",
                "conducted competitive analysis", "coordinated product launches",
                "built sales enablement materials", "gathered customer insights"
            ],
            "metrics": [
                "Product launch success metrics",
                "Adoption / usage rates",
                "Sales enablement impact",
                "Market share growth"
            ],
            "skill_priorities": {
                "high": ["Positioning & messaging", "Go-to-market strategy", "Competitive analysis", "Cross-functional collaboration"],
                "medium": ["Analytics tools", "CRM systems", "Presentation tools"],
                "low": ["Technical programming", "Design tools"]
            },
            "terminology": [
                "go-to-market (GTM)", "positioning", "messaging",
                "competitive analysis", "sales enablement", "product launch"
            ]
        }
    },

    "Education": {
        "Teaching (K-12, Higher Ed)": {
            "emphasis": [
                "Curriculum delivery and lesson planning",
                "Student engagement and assessment",
                "Classroom management",
                "Differentiated instruction",
                "Parent and stakeholder communication",
                "Learning outcome improvement"
            ],
            "language_patterns": [
                "designed lesson plans", "delivered instruction",
                "assessed student progress", "managed classroom environment",
                "differentiated instruction for diverse learners",
                "communicated with parents/stakeholders", "improved student outcomes"
            ],
            "metrics": [
                "Student performance / test scores",
                "Engagement and attendance rates",
                "Learning outcome improvements",
                "Class / course completion rates"
            ],
            "skill_priorities": {
                "high": ["Curriculum development", "Classroom management", "Assessment design", "Subject-matter expertise"],
                "medium": ["Learning management systems (Canvas, Google Classroom)", "Educational technology"],
                "low": ["Software engineering", "Data analysis tools"]
            },
            "terminology": [
                "curriculum", "lesson planning", "differentiated instruction",
                "formative/summative assessment", "classroom management", "learning outcomes"
            ]
        },

        "Educational Administration": {
            "emphasis": [
                "School or program operations management",
                "Policy implementation",
                "Staff supervision and development",
                "Budget management",
                "Stakeholder relations",
                "Compliance with education regulations"
            ],
            "language_patterns": [
                "managed school/program operations", "supervised staff",
                "implemented policies", "managed budgets", "ensured regulatory compliance",
                "built stakeholder relationships", "improved operational efficiency"
            ],
            "metrics": [
                "Operational efficiency improvements",
                "Budget management accuracy",
                "Staff retention",
                "Compliance rate"
            ],
            "skill_priorities": {
                "high": ["Operations management", "Policy implementation", "Staff supervision", "Budget management"],
                "medium": ["Education regulations", "Excel", "Stakeholder communication"],
                "low": ["Technical programming", "Clinical skills"]
            },
            "terminology": [
                "education policy", "accreditation", "staff development",
                "school operations", "compliance", "stakeholder engagement"
            ]
        },

        "Curriculum Development": {
            "emphasis": [
                "Curriculum design and alignment to standards",
                "Instructional material development",
                "Assessment design",
                "Teacher training and support",
                "Learning outcome evaluation",
                "Cross-disciplinary collaboration"
            ],
            "language_patterns": [
                "designed curriculum", "aligned materials to standards",
                "developed instructional materials", "trained teachers on new curriculum",
                "evaluated learning outcomes", "collaborated with educators"
            ],
            "metrics": [
                "Curriculum adoption rate",
                "Learning outcome improvements",
                "Teacher satisfaction / feedback",
                "Standards alignment accuracy"
            ],
            "skill_priorities": {
                "high": ["Curriculum design", "Standards alignment", "Instructional design", "Assessment design"],
                "medium": ["Learning management systems", "Educational research"],
                "low": ["Software engineering", "Data analysis tools"]
            },
            "terminology": [
                "curriculum design", "standards alignment", "instructional design",
                "learning objectives", "backward design", "assessment"
            ]
        },

        "Educational Technology": {
            "emphasis": [
                "EdTech tool implementation and adoption",
                "Blended and online learning design",
                "Teacher and student technology training",
                "Learning management systems",
                "Digital content development",
                "Technology integration strategy"
            ],
            "language_patterns": [
                "implemented EdTech tools", "designed online/blended learning experiences",
                "trained teachers and students on technology", "managed learning management systems",
                "developed digital content", "increased technology adoption"
            ],
            "metrics": [
                "Technology adoption rate",
                "Student engagement with digital tools",
                "Training completion rates",
                "Learning outcome improvements"
            ],
            "skill_priorities": {
                "high": ["Learning management systems (Canvas, Google Classroom, Blackboard)", "Instructional design", "EdTech tools"],
                "medium": ["Basic web/content development", "Data analysis"],
                "low": ["Software engineering", "Clinical skills"]
            },
            "terminology": [
                "LMS", "blended learning", "instructional design",
                "digital literacy", "technology integration", "e-learning"
            ]
        }
    },

    "Operations": {
        "Operations Management": {
            "emphasis": [
                "Process design and efficiency",
                "Team and resource coordination",
                "Performance metrics and KPIs",
                "Cross-functional collaboration",
                "Cost management",
                "Continuous improvement"
            ],
            "language_patterns": [
                "managed operations", "improved process efficiency",
                "coordinated cross-functional teams", "tracked performance metrics",
                "reduced costs", "implemented continuous improvement initiatives"
            ],
            "metrics": [
                "Operational efficiency improvements",
                "Cost savings",
                "Process cycle time reduction",
                "Team productivity"
            ],
            "skill_priorities": {
                "high": ["Process management", "Operations planning", "KPI tracking", "Excel"],
                "medium": ["ERP systems", "Project management tools", "Six Sigma/Lean"],
                "low": ["Software engineering", "Design tools"]
            },
            "terminology": [
                "operations management", "process optimization", "KPIs",
                "continuous improvement", "Lean", "cross-functional coordination"
            ]
        },

        "Supply Chain": {
            "emphasis": [
                "Logistics and inventory management",
                "Supplier and vendor relationship management",
                "Demand forecasting and planning",
                "Procurement",
                "Cost optimization",
                "Supply chain risk management"
            ],
            "language_patterns": [
                "managed supply chain operations", "optimized inventory levels",
                "negotiated with suppliers", "forecasted demand",
                "reduced procurement costs", "mitigated supply chain risk",
                "improved logistics efficiency"
            ],
            "metrics": [
                "Inventory turnover",
                "On-time delivery rate",
                "Cost savings",
                "Lead time reduction"
            ],
            "skill_priorities": {
                "high": ["Supply chain management", "Inventory management", "ERP systems (SAP)"],
                "medium": ["Excel", "Demand forecasting tools", "Procurement"],
                "low": ["Software engineering", "Design tools"]
            },
            "terminology": [
                "supply chain", "logistics", "inventory management",
                "demand forecasting", "procurement", "vendor management", "lead time"
            ]
        },

        "Process Improvement": {
            "emphasis": [
                "Process mapping and analysis",
                "Root cause identification",
                "Efficiency and waste reduction",
                "Lean/Six Sigma methodology",
                "Change management",
                "Cross-functional implementation"
            ],
            "language_patterns": [
                "mapped and analyzed processes", "identified root causes",
                "implemented Lean/Six Sigma initiatives", "reduced waste and inefficiency",
                "led change management", "improved process performance"
            ],
            "metrics": [
                "Process cycle time reduction",
                "Cost / waste reduction",
                "Efficiency improvements",
                "Defect rate reduction"
            ],
            "skill_priorities": {
                "high": ["Lean/Six Sigma", "Process mapping", "Root cause analysis", "Data analysis"],
                "medium": ["Excel", "Project management tools", "Statistical analysis"],
                "low": ["Software engineering", "Design tools"]
            },
            "terminology": [
                "Lean", "Six Sigma", "root cause analysis", "process mapping",
                "waste reduction", "continuous improvement", "kaizen"
            ]
        },

        "Quality Assurance": {
            "emphasis": [
                "Quality standards and compliance",
                "Inspection and testing processes",
                "Root cause analysis for defects",
                "Process and quality audits",
                "Continuous improvement",
                "Cross-functional quality collaboration"
            ],
            "language_patterns": [
                "ensured quality compliance", "conducted inspections/audits",
                "identified and resolved defects", "implemented quality standards",
                "reduced defect rates", "led continuous improvement initiatives"
            ],
            "metrics": [
                "Defect rate reduction",
                "Compliance rate",
                "Audit pass rate",
                "Customer complaint reduction"
            ],
            "skill_priorities": {
                "high": ["Quality management systems", "Root cause analysis", "Inspection/audit processes"],
                "medium": ["Six Sigma", "Statistical process control", "Excel"],
                "low": ["Software engineering", "Design tools"]
            },
            "terminology": [
                "quality assurance", "quality control", "ISO standards",
                "defect rate", "root cause analysis", "audits", "compliance"
            ]
        }
    },

    "Consulting": {
        "Management Consulting": {
            "emphasis": [
                "Strategic problem-solving and analysis",
                "Client engagement and stakeholder management",
                "Data-driven recommendations",
                "Cross-industry adaptability",
                "Presentation and storytelling",
                "Project and engagement management"
            ],
            "language_patterns": [
                "led client engagements", "conducted strategic analysis",
                "developed data-driven recommendations", "presented findings to executives",
                "managed project workstreams", "drove organizational change"
            ],
            "metrics": [
                "Client impact / value delivered",
                "Engagement success metrics",
                "Recommendation adoption rate",
                "Project delivery timeliness"
            ],
            "skill_priorities": {
                "high": ["Strategic analysis", "Excel", "PowerPoint", "Problem-solving frameworks"],
                "medium": ["SQL/Python for analysis", "Project management", "Market research"],
                "low": ["Software engineering", "Design tools"]
            },
            "terminology": [
                "strategic analysis", "stakeholder management", "client engagement",
                "problem-solving frameworks", "executive presentations", "change management"
            ]
        },

        "Technology Consulting": {
            "emphasis": [
                "Technology strategy and advisory",
                "System implementation support",
                "Client requirements gathering",
                "Digital transformation",
                "Technical solution design",
                "Stakeholder communication"
            ],
            "language_patterns": [
                "advised clients on technology strategy", "led system implementations",
                "gathered technical requirements", "supported digital transformation initiatives",
                "designed technical solutions", "presented to stakeholders"
            ],
            "metrics": [
                "Implementation success rate",
                "Client satisfaction",
                "Project delivery timeliness",
                "Cost / efficiency improvements delivered"
            ],
            "skill_priorities": {
                "high": ["Technology strategy", "Systems analysis", "Project management", "Client communication"],
                "medium": ["SQL", "Cloud platforms", "ERP systems"],
                "low": ["Deep software engineering (unless relevant)", "Design tools"]
            },
            "terminology": [
                "digital transformation", "technology strategy", "systems implementation",
                "requirements gathering", "solution architecture"
            ]
        },

        "Financial Consulting": {
            "emphasis": [
                "Financial advisory and analysis",
                "Client financial strategy",
                "Valuation and modeling",
                "Due diligence support",
                "Regulatory and compliance advisory",
                "Client relationship management"
            ],
            "language_patterns": [
                "advised clients on financial strategy", "built financial models",
                "supported due diligence", "conducted valuation analysis",
                "ensured regulatory compliance", "presented recommendations to clients"
            ],
            "metrics": [
                "Client value / cost savings delivered",
                "Deal / engagement success rate",
                "Forecast / model accuracy",
                "Client retention"
            ],
            "skill_priorities": {
                "high": ["Financial modeling", "Valuation", "Excel", "Client advisory"],
                "medium": ["SQL", "PowerPoint", "Regulatory frameworks"],
                "low": ["Software engineering", "Design tools"]
            },
            "terminology": [
                "financial advisory", "valuation", "due diligence",
                "financial modeling", "client strategy", "regulatory compliance"
            ]
        }
    },

    "General / Hybrid": {
        "Project Management": {
            "emphasis": [
                "Project planning and scheduling",
                "Cross-functional team coordination",
                "Risk and budget management",
                "Stakeholder communication",
                "Timeline and milestone tracking",
                "Process/methodology adherence (Agile/Waterfall)"
            ],
            "language_patterns": [
                "managed projects end-to-end", "coordinated cross-functional teams",
                "tracked project timelines and budgets", "mitigated risks",
                "communicated with stakeholders", "delivered projects on time and within budget"
            ],
            "metrics": [
                "On-time delivery rate",
                "Budget adherence",
                "Stakeholder satisfaction",
                "Risk mitigation effectiveness"
            ],
            "skill_priorities": {
                "high": ["Project management tools (Jira, Asana, MS Project)", "Agile/Scrum", "Stakeholder communication"],
                "medium": ["Excel", "Budget management", "Risk management"],
                "low": ["Deep technical/software engineering (unless relevant)"]
            },
            "terminology": [
                "Agile", "Scrum", "project scope", "milestones",
                "stakeholder management", "risk management", "Gantt charts"
            ]
        },

        "Business Analysis": {
            "emphasis": [
                "Requirements gathering and documentation",
                "Process analysis and improvement",
                "Data-driven insights",
                "Stakeholder communication",
                "Solution and gap analysis",
                "Cross-functional collaboration"
            ],
            "language_patterns": [
                "gathered and documented requirements", "analyzed business processes",
                "identified gaps and improvement opportunities", "translated business needs into solutions",
                "presented insights to stakeholders", "collaborated with cross-functional teams"
            ],
            "metrics": [
                "Process improvement impact",
                "Requirements accuracy",
                "Stakeholder satisfaction",
                "Project/solution adoption rate"
            ],
            "skill_priorities": {
                "high": ["Requirements gathering", "Process mapping", "Excel", "SQL"],
                "medium": ["Data visualization (Tableau/Power BI)", "Business process modeling"],
                "low": ["Software engineering", "Design tools"]
            },
            "terminology": [
                "requirements gathering", "business process modeling", "gap analysis",
                "stakeholder management", "use cases", "SDLC"
            ]
        },

        "General Business": {
            "emphasis": [
                "Cross-functional collaboration and execution",
                "Business operations support",
                "Data-informed decision-making",
                "Communication and stakeholder relationships",
                "Adaptability across business functions",
                "Process execution"
            ],
            "language_patterns": [
                "supported business operations", "collaborated across teams",
                "analyzed data to inform decisions", "communicated with stakeholders",
                "executed on business initiatives", "contributed to process improvements"
            ],
            "metrics": [
                "Operational efficiency contributions",
                "Stakeholder satisfaction",
                "Task / initiative completion rate",
                "Business impact"
            ],
            "skill_priorities": {
                "high": ["Excel", "Communication", "Business acumen", "Project coordination"],
                "medium": ["PowerPoint", "Basic data analysis", "CRM systems"],
                "low": ["Deep technical programming", "Design tools"]
            },
            "terminology": [
                "cross-functional collaboration", "business operations",
                "stakeholder communication", "process execution", "business acumen"
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
