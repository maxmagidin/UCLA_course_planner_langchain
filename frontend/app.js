const $ = (id) => document.getElementById(id);

const presets = {
  openai: { provider: "openai", base_url: "https://api.openai.com/v1", model: "gpt-4o-mini" },
  openrouter: { provider: "openai_compatible", base_url: "https://openrouter.ai/api/v1", model: "openai/gpt-4o-mini" },
  asi_one: { provider: "asi_one", base_url: "https://api.asi1.ai/v1", model: "asi1" },
  custom: { provider: "openai_compatible", base_url: "", model: "" },
};

const splitList = (value) => value.split(/[,;\n]/).map((item) => item.trim()).filter(Boolean);
const splitConstraints = (value) => value.split(/[;\n]/).map((item) => item.trim()).filter(Boolean);

function setStatus(element, message, error = false) {
  element.textContent = message;
  element.classList.toggle("error", error);
}

function showDetails() {
  $("detailsStep").hidden = false;
  $("detailsStep").scrollIntoView({ behavior: "smooth", block: "start" });
}

function applyHints(hints = {}) {
  if (hints.name) $("name").value = hints.name;
  if (hints.major) $("major").value = hints.major;
  if (hints.year) $("year").value = hints.year;
  if (hints.gpa !== undefined) $("gpa").value = hints.gpa;
  if (hints.units_completed !== undefined) $("units").value = hints.units_completed;
}

function reviewCourses(codes) {
  $("darsCourses").value = codes.join(", ");
  $("courseCount").textContent = `${codes.length} course code${codes.length === 1 ? "" : "s"} found`;
  $("darsReview").hidden = false;
}

async function fileBase64() {
  const file = $("darsPdf").files[0];
  if (!file) return null;
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function request(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "The request could not be completed.");
  return data;
}

function profile() {
  return {
    name: $("name").value.trim(),
    major: $("major").value.trim(),
    year: $("year").value,
    gpa: Number($("gpa").value || 0),
    units_completed: Number($("units").value || 0),
    enrollment_pass: $("pass").value,
    pass_open_datetime: $("passOpen").value.trim(),
    term: $("term").value.trim(),
    dars_courses: splitList($("darsCourses").value),
    required_courses: splitList($("required").value),
    preferred_courses: splitList($("preferred").value),
    hard_constraints: splitConstraints($("constraints").value),
    format_preference: $("format").value,
    min_units: Number($("minUnits").value),
    max_units: Number($("maxUnits").value),
  };
}

function validateProfile(value) {
  if (!value.name) return "Add the student's name.";
  if (!value.major) return "Add the student's major.";
  if (!value.term) return "Add the UCLA term to plan.";
  if (!value.required_courses.length) return "Add at least one course you need.";
  if (value.max_units < value.min_units) return "Maximum units must be at least the minimum units.";
  return null;
}

function fillProfile(value) {
  const fieldMap = {
    name: "name", major: "major", year: "year", gpa: "gpa",
    units_completed: "units", enrollment_pass: "pass",
    pass_open_datetime: "passOpen", term: "term",
    format_preference: "format", min_units: "minUnits", max_units: "maxUnits",
  };
  Object.entries(fieldMap).forEach(([key, id]) => {
    if (value[key] !== undefined && value[key] !== null) $(id).value = value[key];
  });
  if (value.dars_courses?.length) reviewCourses(value.dars_courses);
  $("required").value = (value.required_courses || []).join(", ");
  $("preferred").value = (value.preferred_courses || []).join(", ");
  $("constraints").value = (value.hard_constraints || []).join("; ");
}

$("darsPdf").addEventListener("change", () => {
  const file = $("darsPdf").files[0];
  $("fileLabel").textContent = file ? file.name : "Choose a DARS PDF";
});

$("parseButton").addEventListener("click", async () => {
  const button = $("parseButton");
  button.disabled = true;
  setStatus($("parseStatus"), "Reading your DARS…");
  try {
    const dars_pdf_base64 = await fileBase64();
    const dars_text = $("darsText").value.trim() || null;
    if (!dars_pdf_base64 && !dars_text) throw new Error("Choose a PDF or paste DARS text first.");
    const data = await request("/dars/parse", { dars_text, dars_pdf_base64 });
    reviewCourses(data.course_codes);
    applyHints(data.profile_hints);
    setStatus($("parseStatus"), `DARS read successfully from ${data.source}. Review the extracted information below.`);
    showDetails();
  } catch (error) {
    setStatus($("parseStatus"), error.message, true);
  } finally {
    button.disabled = false;
  }
});

$("skipButton").addEventListener("click", () => {
  reviewCourses([]);
  setStatus($("parseStatus"), "Continuing without a DARS report.");
  showDetails();
});

$("exampleButton").addEventListener("click", () => {
  reviewCourses(["MATH 31A"]);
  fillProfile({
    name: "Alex Student", major: "Computer Science", year: "junior", gpa: 3.6,
    units_completed: 96, enrollment_pass: "pass_1", pass_open_datetime: "2026-08-28 09:00",
    term: "Fall 2026", required_courses: ["COM SCI 31", "COM SCI 32", "COM SCI 111"],
    preferred_courses: [], hard_constraints: [], format_preference: "any", min_units: 12, max_units: 16,
  });
  setStatus($("parseStatus"), "Loaded the working Fall 2026 test profile.");
  showDetails();
});

function updateProviderPreset() {
  const selected = $("providerPreset").value;
  const preset = presets[selected];
  $("modelName").value = preset.model;
  $("baseUrl").value = preset.base_url;
  $("baseUrlField").hidden = selected !== "custom";
}

$("providerPreset").addEventListener("change", updateProviderPreset);
updateProviderPreset();

$("autofillButton").addEventListener("click", async () => {
  const button = $("autofillButton");
  const message = $("byokMessage").value.trim();
  const apiKey = $("apiKey").value;
  if (!message || !apiKey) {
    setStatus($("autofillStatus"), "Add your planning details and model API key first.", true);
    return;
  }
  const preset = presets[$("providerPreset").value];
  const courses = splitList($("darsCourses").value);
  const content = [
    message,
    courses.length ? `DARS courses completed or in progress: ${courses.join(", ")}.` : "",
  ].filter(Boolean).join("\n");
  button.disabled = true;
  setStatus($("autofillStatus"), "Asking your model to structure these details…");
  try {
    const data = await request("/intake", {
      conversation: [{ role: "user", content }],
      model: {
        provider: preset.provider,
        api_key: apiKey,
        base_url: $("baseUrl").value.trim() || preset.base_url,
        model: $("modelName").value.trim(),
      },
    });
    fillProfile(data);
    setStatus($("autofillStatus"), "Planning details filled. Review them, then run the planner.");
  } catch (error) {
    setStatus($("autofillStatus"), error.message, true);
  } finally {
    button.disabled = false;
  }
});

$("planButton").addEventListener("click", async () => {
  const button = $("planButton");
  const value = profile();
  const validationError = validateProfile(value);
  if (validationError) {
    setStatus($("planStatus"), validationError, true);
    return;
  }
  button.disabled = true;
  setStatus($("planStatus"), "Building schedules from live UCLA data…");
  try {
    const data = await request("/plan", { profile: value });
    $("result").textContent = data.report_markdown || JSON.stringify(data, null, 2);
    $("resultSummary").textContent = `${data.candidates.length} schedule candidate${data.candidates.length === 1 ? "" : "s"} · ${data.status}`;
    $("resultStep").hidden = false;
    setStatus($("planStatus"), "Planning complete.");
    $("resultStep").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    setStatus($("planStatus"), error.message, true);
  } finally {
    button.disabled = false;
  }
});
