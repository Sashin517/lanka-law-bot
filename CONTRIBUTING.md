# Contributing to LankaLawBot ⚖️

Welcome to the LankaLawBot development team! To ensure our Capstone project remains stable, professional, and free of merge conflicts, all team members must follow the strict Git workflow outlined below.

---

## 1. Active Feature Branches 🌿
We are currently working across specific feature branches grouped by stack. **Please ensure you are pushing your commits to the correct active branch.** ### Frontend UI Branches (Sashin & Deshapriya)
* `feature/ui-research-dashboard`: Building the Research layout. Implements the sidebar, search bar, result cards, and the "Added materials" state logic.
* `feature/ui-drafting-workspace`: Building the Drafting layout. Integrates the rich text editor and the side-by-side document viewer component.

### Backend Agent Branches
* `feature/agent-advanced-search`: Upgrading `agent.py` to add ChromaDB metadata filtering (accepting parameters like `source_type="acts"` and `date_range="last_5_years"`).
* `feature/agent-drafter`: Creating the legal writing LangChain agent that accepts retrieved documents and outputs a structured legal opinion/contract.
* `feature/agent-reviewer`: Creating the verification agent (strict senior partner persona) to review generated drafts for legal accuracy.

### API Integration Branch
* `feature/api-multi-agent-router`: Upgrading `main.py` in FastAPI to route traffic to separate endpoints (`/api/search`, `/api/draft`, `/api/verify`).

*(Note: For future tasks or bug fixes, please use the standard format: `type/what-is-being-done`, such as `bugfix/sidebar-state-error`)*

---

## 2. The Pull Request (PR) Rules 🚦
The `main` branch is **protected**. You cannot push code directly to `main`.

1. **Branch Out:** Always write your code on your assigned `feature/` branch.
2. **Open a PR:** When your feature is complete and tested locally, go to GitHub and open a Pull Request to merge your branch into `main`.
3. **Review & Approve:** Every PR requires at least **one (1) approval** from another team member before the Merge button is unlocked. Please review your teammates' code carefully!
4. **Stay Up-to-Date:** If someone else merged code into `main` while you were working, GitHub will require you to update your branch with their latest changes before you can merge.

---

## 3. Automated CI/CD Checks 🤖
We have a GitHub Actions pipeline (`ci.yml`) acting as our automated referee. Whenever you open a PR, the server will automatically check:
* **Build Next.js:** Ensures the React frontend compiles without errors.
* **Install Python Backend:** Ensures the Python `requirements.txt` installs successfully.

**If the checks fail:** The PR will be blocked. You must read the error log, fix the code on your local machine, and push the fix to your branch.

---

## 4. Local Database Setup (DO NOT PUSH) 🗄️
Because vector databases are heavy, the `chroma_db` folder is ignored by Git. 

**When you clone this repo for the first time:**
1. Do not run the data chunking script unless you are modifying the dataset.
2. Download the pre-built `chroma_db.zip` from our shared Google Drive.
3. Extract it and place the folder exactly at: `backend/database/chroma_db/`.

---

*Let's build an incredible project!* 🚀