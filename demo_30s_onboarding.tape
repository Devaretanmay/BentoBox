Output demo_30s_onboarding.gif
Output demo_30s_onboarding.mp4

Set FontSize 18
Set Width 1150
Set Height 720
Set Padding 24
Set LineHeight 1.35
Set Theme "Catppuccin Mocha"
Set WindowBar Colorful
Set TypingSpeed 35ms

# Silently prepare clean environment and custom prompt before recording begins
Hide
Type "/tmp/setup_30s_demo.sh && cd /tmp/billing_service_demo && export PS1='billing-service (main) $ ' && clear"
Enter
Sleep 1s
Show

# ── 1. INIT: Create the Compart workspace (0:00–0:06) ────────────────────────
# Voiceover: "Compart starts exactly where Git does. I initialize it inside my project, and it creates a workspace for my agents."
Sleep 500ms
Type "compart init"
Enter
Sleep 3.5s

# ── 2. CONFIGURE: Inspect Declared Compartments (0:06–0:13) ──────────────────
# Voiceover: "I define the environments I want. Research can read but not modify. Builder can write. Tester can execute but can't reach the network."
Type "compart inspect"
Enter
Sleep 4.5s

# ── 3. BUILD: Add Workflow Steps & Show DAG (0:13–0:21) ──────────────────────
# Voiceover: "Finally, I define how the work should flow. Each step runs in its own compartment."
Type "compart -w stripe-webhook"
Enter
Sleep 2s

Hide
Type "compart step stripe-webhook src/research.py --compartment research > /dev/null 2>&1 && compart step stripe-webhook src/build.py --compartment builder > /dev/null 2>&1 && compart step stripe-webhook 'pytest tests/' --compartment tester > /dev/null 2>&1"
Enter
Sleep 500ms
Show

Type "compart workflow show stripe-webhook"
Enter
Sleep 4.5s

# ── 4. PUNCHLINE: The Agent Workspace Primitive (0:21–0:28) ──────────────────
# Voiceover: "That's Compart. Initialize your workspace, define your compartments, and compose your agent workflow. Your agents come later."
Type "/tmp/render_30s_punchline.sh"
Enter
Sleep 6s
