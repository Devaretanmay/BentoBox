Output demo_30s_onboarding.gif
Output demo_30s_onboarding.mp4

Set FontSize 18
Set Width 1150
Set Height 720
Set Padding 24
Set LineHeight 1.35
Set Theme "Catppuccin Mocha"
Set WindowBar Colorful
Set TypingSpeed 25ms

# Silently prepare clean environment and custom prompt
Type "/tmp/setup_30s_demo.sh > /dev/null 2>&1"
Enter
Sleep 300ms

Type "cd /tmp/billing_service_demo && export PS1='billing-service (main) $ ' && clear"
Enter
Sleep 500ms

# ── 1. INIT: Create the Compart workspace (0:00–0:06) ────────────────────────
# Voiceover: "Compart starts exactly where Git does. I initialize it inside my project, and it creates a workspace for my agents."
Type "compart init"
Enter
Sleep 2.5s

# ── 2. CONFIGURE: Inspect Declared Compartments (0:06–0:13) ──────────────────
# Voiceover: "I define the environments I want. Research can read but not modify. Builder can write. Tester can execute but can't reach the network."
Type "compart inspect"
Enter
Sleep 2.5s

# ── 3. BUILD: Add Workflow Steps & Show DAG (0:13–0:20) ──────────────────────
# Voiceover: "Finally, I define how the work should flow. Each step runs in its own compartment."
Type "compart -w stripe-webhook"
Enter
Sleep 1s

Type "compart step stripe-webhook src/research.py --compartment research > /dev/null 2>&1 && compart step stripe-webhook src/build.py --compartment builder > /dev/null 2>&1 && compart step stripe-webhook 'pytest tests/' --compartment tester > /dev/null 2>&1"
Enter
Sleep 300ms

Type "compart workflow show stripe-webhook"
Enter
Sleep 3s

# ── 4. PUNCHLINE: The Agent Workspace Primitive (0:20–0:28) ──────────────────
# Voiceover: "That's Compart. Initialize your workspace, define your compartments, and compose your agent workflow. Your agents come later."
Type "/tmp/render_30s_punchline.sh"
Enter
Sleep 4.5s
