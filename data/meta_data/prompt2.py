SYSTEM_PROMPT = """
You are an expert scientific reasoner and problem-solver, training a world-class scientific research assistant AI. Your primary task is to devise and articulate logical solutions to experimental challenges. You will express these solutions in a high-quality, structured format based on the context of a provided scientific protocol.
You will be given a Scientific Experiment Protocol in a structured JSON format. Your generated response must strictly adhere to the following XML structure:
<question>
[A clear, relevant question you formulate that poses a scientific challenge or query.]
</question>
<think>
[This is the core of your response. Articulate the scientific strategy to solve the problem in the question. Start by analyzing the goal, then formulate a hypothesis or a clear plan of attack. Justify why the proposed sequence of actions is the most logical and effective approach. This must reflect the critical thinking of a scientist.]
</think>
<key>
[The structured, machine-readable plan derived from the reasoning in the <think> tag. Each step represents a single, atomic action.]
Step 1: {"action": "detach", "objects": ["bmdcs"], "parameters": ["1x pbs-5 mm edta", "10 min", "37 °c"]}
Step 2: {"action": "wash", "objects": ["cells"], "parameters": ["1x pbs", "twice"]}
Step 3: {"action": "centrifuge", "objects": ["cells"], "parameters": ["367xg", "10 min"]}
...
</key>
<orc>
[A concise, natural-language summary of the plan in <key>. Each step must be an imperative sentence.]
Step 1: Detach bmdcs with 1x pbs-5 mm edta for 10 min at 37 °c.
Step 2: Wash the cells with 1x pbs twice.
Step 3: Centrifuge the cells at 367xg for 10 min.
</orc>
<note>
[A concise paragraph summarizing the most critical safety information relevant to the steps in the plan.]
</note>

1. Role Descriptions
<think> (CRITICAL): The important part of your output. It is the explicit, step-by-step scientific reasoning that justifies the plan presented in <key>. It must bridge the gap between the problem in the <question> and the solution in the <key>.
<orc> (Natural Language Summary): This section translates each step from the <key> tag into a simple, human-readable instruction. Each step must be a concise, imperative (command) sentence that strictly reflects the action, objects, and parameters of the corresponding step in <key>, adding no new information. The number of steps must match <key> exactly.

2. <key> Formatting Rules (CRITICAL)
1) One Action Per Step: Each Step must correspond to a single, atomic action and contain exactly one JSON dictionary. If a logical operation requires multiple actions (e.g., 'wash and then centrifuge'), you must break it down into sequential, separate steps.
- Source: "Stop the reaction by adding cold PBS and placing the tubes on ice."
- Correct Breakdown:
    Step 1: {"action": "add", "objects": ["cold pbs"], "parameters": ["to stop reaction"]}
    Step 2: {"action": "place", "objects": ["tubes"], "parameters": ["on ice"]}
2) Lowercase Content: All string values within the JSON object (action, elements in objects, and elements in parameters) must be in lowercase. Numbers and standard units (e.g., °C, xg, mM) are exempt.
3) Structure of Each Action:
"action": A string containing a single, concise verb in lowercase (e.g., "add", "incubate", "centrifuge", "wash").
"objects": A list of strings. These are the direct objects of the action, in lowercase. Use specific, meaningful nouns (e.g., "bmdcs", "cell pellet", "1x pbs").
"parameters": A list of strings that modify the action, in lowercase. This includes quantities, durations, temperatures, speeds, and key conditions.
4) Parameter-Object Relationship: Parameters in the "parameters" list must apply jointly to the action performed on all objects in the "objects" list.
5) Conciseness and Semantic Distillation: Your primary goal is to distill the core scientific action, not to transcribe the original text verbatim. Simplify verbose language into concise keywords or short phrases.
- Bad (Verbose): "parameters": ["in a water bath set at 37 °c"]
- Good (Concise & Distilled): "parameters": ["37 °c", "in water bath"]
"""

TYPE_INSTRUCTIONS = {
    "retrieval": "Generate a data sample that demands precise extraction of factual, lab-ready parameters from authoritative sources, emphasizing exact values, units, tolerances, environmental conditions, and contextual qualifiers (e.g., temperature, pH, grade, catalog numbers) that can be directly transcribed into protocol fields; require cross-checking for consistency across related parameters (stock vs. working concentrations, volumes vs. instrument ranges), explicit unit normalization, correct significant figures, and clear source attribution or provenance notes; the scenario should penalize guesswork and reward verifiability, internal coherence, and readiness for immediate use without human reinterpretation.",
    "planning": "Generate questions that demand the model translate a high-level research objective into a granular, step-by-step, executable experimental workflow. These prompts should challenge the model to logically sequence actions, identify necessary inputs and outputs for each stage, specify required equipment and reagents, and integrate quality control checkpoints. The aim is to assess the model's ability to understand dependencies, allocate resources, and construct a coherent experimental plan that is both feasible and reproducible. Focus on scenarios where multiple steps are interconnected, requiring a holistic understanding of the scientific process, from sample preparation to final analysis. The generated data should reflect the thought process of designing a robust, end-to-end experiment.",
    "troubleshooting": "Your task is to create questions that simulate real-world experimental failures or unexpected outcomes, requiring the model to systematically diagnose problems and propose actionable, testable solutions. These prompts should present a specific symptom or deviation from expected results. The model should then identify potential causes, prioritize them, suggest specific, single-variable corrective actions, and outline how to verify the fix. The generated data should encourage iterative problem-solving, mimicking the 'observe-hypothesize-test-verify' cycle crucial for resilience and efficiency in research. Think about common issues in various lab techniques (e.g., PCR, Western blot, cell culture contamination) where a methodical approach to error resolution is paramount.",
    "constraint": "Generate questions that require the model to adapt experimental plans under non-ideal, constrained conditions. These prompts should present a scenario where a critical resource (e.g., specific reagent, equipment, budget, time, or computational power) is unavailable or limited. The model needs to identify acceptable alternative methods or materials that can still achieve the core experimental objective, while clearly articulating the trade-offs involved (e.g., cost, efficiency, sensitivity, comparability of results). The goal is to train the model to be flexible and pragmatic, capable of navigating 'Constraint Satisfaction Problems' in a lab setting and preventing dead ends when ideal conditions are not met. Consider real-world limitations that often arise in resource-limited environments.",
    "scaling": "Your task is to create questions that test the model's essential practical skills in unit conversion, stoichiometric calculations, and scaling experimental protocols. These prompts should involve adjusting reaction volumes, reagent concentrations, or sample sizes while maintaining critical ratios and ensuring technical feasibility (e.g., considering minimum pipetting volumes, solubility limits, or required excess for practical handling). The aim is to train the model to accurately translate theoretical recipes into precise, actionable laboratory instructions, preventing errors arising from incorrect calculations or impractical volumes. Focus on scenarios where a protocol needs to be scaled up or down, or where units need to be consistently converted for different components.",
    "safety": "Generate questions that prompt the model to proactively identify and address potential hazards associated with specific chemicals, biological materials, or procedures. The model should automatically append necessary safety precautions, personal protective equipment (PPE) requirements, waste disposal guidelines, and compliance reminders, even if not explicitly asked. The goal is to train the model to inherently integrate critical safety and regulatory information into any advice it provides, minimizing risks in a laboratory setting. Think about scenarios involving hazardous chemicals, biohazardous materials, specialized equipment, or waste generation, where adherence to safety protocols and regulatory standards (e.g., OSHA, institutional biosafety guidelines) is non-negotiable.",
     "overview_qa": "Generate a question asking for a high-level summary of an experimental workflow. The goal is to provide a concise 'bird's-eye view' of the major stages while preserving the logical sequence. The generated `<key>` should be concise, containing approximately 2 to 6 steps. To achieve this, intelligently select the appropriate level of the `hierarchical_protocol` to summarize: if the top-level sections are few enough to fit this length, summarize their titles. If there are too many top-level sections, choose a single, major first-level section and summarize the titles of its second-level sub-sections instead.",
    "specific_step_qa": "Generate a question that asks for a granular, step-by-step breakdown of a specific, continuous segment of the experiment. The question must target **exactly one major first-level section** from the `hierarchical_protocol`. Crucially, you must **select a section of appropriate length** such that its detailed procedural breakdown results in a concise `<key>` of approximately 2 to 6 atomic steps. Avoid selecting sections that are either too simple (1 step) or overly complex (7+ steps). The `<key>` answer must be derived from the **lowest-level procedural text** within that single section, not its titles, adhering to all distillation and formatting rules."
}

USER_PROMPT_TEMPLATE_LEVEL2 = """
[Protocol Data]
Title: {title}
Abstract: {abstract}
Problem Statement: {problem}
Methodology: {method}
Innovation: {innovation}
Application: {application}
Materials & Equipment: {input}
Procedure: {hierarchical_protocol}

You are now tasked with generating {num_qa} high-quality, single-turn QA pair(s) for the {type_name} category.
Task Details for Category: {type_name}
Your task is guided by the following definition: {type_instruction}

Core Instructions and Examples
1. Primary Goal: Create Diverse and Self-Contained Questions
Your primary goal is to generate questions that are not only information-rich but also varied in their structure and phrasing. Avoid using repetitive sentence templates for every question. Each question must be fully self-contained, allowing a user to understand the query without needing to see the original protocol. To achieve this, you must skillfully embed context from the protocol's metadata (Title, Abstract, Problem Statement, Methodology, Materials & Equipment etc.)  into the question itself.
Here are several strategies to ensure question diversity. You should actively combine these strategies.
- Strategy 1: Vary the SCOPE of the Inquiry (Instead of always asking for a full multi-step procedure, narrow or broaden the focus.)
    Standard Scope (Good): "What is the procedure for washing the cells after detachment?"
    Micro Scope (Better for diversity): "For the cell wash step in the '{title}' protocol, what is the exact concentration of EDTA required in the 1x PBS buffer, and what is the specified centrifugation speed in xg?"
    Macro Scope (Good for overviews): "What are the three main phases of the '{title}' experiment, from sample preparation to final analysis?"

- Strategy 2: Vary the CONTEXT of the Request (Frame the question around a goal or a specific situation, not just a request for information.)
    Standard Context (Good): "Provide the protocol for the chase phase."
    Goal-Oriented Context (Better for diversity): "To allow for the maturation of early endosomes into lysosomes in the '{title}' experiment, what is the precise 'chase' protocol a researcher must follow after the initial dextran pulse?"
    Situational Context (Excellent for diversity): "A researcher using the '{title}' protocol has just completed the 10-minute pulse at 37°C and needs to stop the reaction. What is the immediate next step, and what is the composition of the buffer used for this?"

- Strategy 3: Vary the FRAMING of the Question (Change the implied user and their need. Are they asking for a checklist, a narrative, or a specific value?)
    Standard Framing (Good): "What are the steps for preparing the pH standard curve?"
    Checklist Framing (Better for diversity): "Provide a checklist of the key actions and reagents needed to generate the pH standard curve in the '{title}' assay, starting from pulsing the cells."
    Parameter-focused Framing (Excellent for diversity): "A lab is setting up the '{title}' experiment. List all critical time and temperature parameters for both the 'pulse' and 'chase' incubation steps."

2. Critical Generation Rules
You must strictly adhere to the following rules for every QA pair you generate:
Rule 1: Source of Truth. The hierarchical_protocol field is the one and only source of truth for constructing the experimental steps within the <key> tag. Do not hallucinate or infer procedures not explicitly mentioned in this field. Use the other metadata fields (Title, Abstract, etc.) primarily for enriching the <question>.
Rule 2: Strict Output Structure. Each generated QA pair must strictly follow the required output structure, including all required tags in this order: <question>, <think>, <key>, <orc>, and <note>. The <orc> tag must be a natural-language summary of the <key> tag, with each step written as a concise imperative sentence. The number of steps in <orc> and <key> must be identical.
Rule 3: Explain the Scientific 'Why' in <think> (Crucial). The <think> tag must concisely articulate the scientific thought process that leads to the experimental plan in <key>. It should focus on the high-level strategy and the core scientific principles justifying the plan, rather than a redundant, step-by-step rehashing of the procedure. Your response must be a standalone scientific explanation, not a meta-commentary on your generation process.
- Do This (Scientific Reasoning): Your reasoning must answer the question, "Why are these steps, in this order, the correct way to solve the experimental problem posed in the <question>?" Start with the overall goal, explain the core scientific principle, and then justify the sequence of operations in <key>, explaining how each action contributes to the final objective.
- Do NOT Do This (Meta-Commentary): Do not describe how you are creating the <key> tag. Avoid phrases like "First, I will parse the protocol...", "To distill this step, I will extract keywords...", or "The provided text is verbose, so I will simplify it to...". Your response must be a standalone scientific explanation.
Rule 4: Radical Distillation and Keyword Extraction (Most Important Rule). The goal of the <key> tag is to achieve maximum semantic distillation. You must aggressively simplify and decompose verbose descriptions into atomic keywords. Avoid using entire phrases or sentences as a value for an object or parameter. Your target is to represent each piece of information with one or two essential words.
Example of Radical Distillation:
    - Original Text: "resuspend the cells in 100ul total volume of prewarmed conditioned complete medium"
    - Bad (Literal Transcription): {{"action": "resuspend", "objects": ["the cells"], "parameters": ["in 100ul total volume of prewarmed conditioned complete medium"]}}
    - Okay (Simple Simplification): {{"action": "resuspend", "objects": ["cells"], "parameters": ["100 µl", "prewarmed conditioned complete medium"]}}
    - Excellent (Radical Distillation): {{"action": "resuspend", "objects": ["cells"], "parameters": ["100 µl", "conditioned complete medium", "prewarmed"]}}
Rule 5: Question-Answer Alignment. The scope of the question you formulate must precisely match the content of the <key> tag. If the question asks for a specific sub-procedure (e.g., "the washing steps"), the <key> should only contain the steps for washing, not the entire protocol.
Rule 6: Handle Insufficient Data Gracefully. If the protocol information is insufficient to create a fully compliant QA pair, you must still produce a plausible, fully formatted QA pair by making reasonable, minor assumptions that are consistent with the protocol's scope. You must clearly state any assumptions you've made within the <think> tag.
Rule 7: Keep the <note> Brief and Focused. The <note> tag must be a single, concise paragraph. It should highlight only the most critical and specific safety hazards directly related to the plan in <key>. Avoid generic or obvious advice.
"""

REPAIR_PROMPT = """Your previous output contained formatting errors and did not meet the required schema. Please correct the output to conform strictly to the structure and rules outlined below.
<question>
[Your generated question text here.]
</question>
<think>
[Your thought process for solving the experimental problem.]
</think>
<key>
Step 1: {"action": "verb1", "objects": ["object1"], "parameters": ["param1"]}
Step 2: {"action": "verb2", "objects": ["object2"], "parameters": ["param2"]}
...
</key>
<orc>
Step 1: Verb1 the object1 with param1.
Step 2: Verb2 the object2 with param2.
...
</orc>
<note>
[Relevant safety and handling information.]
</note>

Mandatory Rules to Follow:
1. Correct Nesting: The root must contain exactly five tags in this specific order: <question>, <think>, <key>, <orc>, and <note>. These are all top-level tags.
2. <key> Step Format: The content inside the <key> tag must be a sequence of steps. Each step must begin with the exact string Step X: (where X is a number starting from 1) followed by a newline.
3. JSON String Value (for <key>): The value for each Step X: in the <key> tag must be a single, valid JSON string.
    This JSON string must parse into a single Dictionary.
    This dictionary must contain exactly three keys: "action", "objects", "parameters".
    All string values (for action, and inside the objects/parameters lists) must be lowercase.
    - Correct Example: Step 1: {"action": "add", "objects": ["pbs"], "parameters": ["10 ml", "cold"]}
    - Incorrect Example (not a valid JSON string): Step 1: {'action': 'add', 'objects': ['pbs']} (Uses single quotes)
    - Incorrect Example (is a list, not a dictionary): Step 1: [{"action": "add", "objects": ["pbs"], "parameters": ["10 ml", "cold"]}]
4. <orc> Summary Format: The <orc> tag must be a natural language summary. The number of Step X: entries must exactly match the number of steps in <key>. Each step must be a single, concise imperative sentence that accurately reflects the corresponding step in <key>.
5. No Extra Commentary: Return only the corrected XML block starting with <question> and ending with </note>. Do not include any apologies, explanations, or any text outside of these tags.
"""



