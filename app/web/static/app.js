const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const sendButton = document.querySelector("#sendButton");
const conversation = document.querySelector("#conversation");
const resetButton = document.querySelector("#resetButton");
const suggestions = document.querySelector("#suggestions");

const translations = {
  en: {
    title: "Course Compass — find your next DTU course", description: "Get personal recommendations from DTU's official course catalogue.",
    brand: "Course Compass", brandLabel: "Course Compass home", status: "Official DTU data", languageLabel: "Choose language", reset: "New chat",
    eyebrow: "Your personal course guide", heroTitle: "From curiosity to<br><em>the right course.</em>", heroCopy: "Tell us what you study and what you want to learn. We will explain your study plan or find relevant courses in DTU's official catalogue.",
    chatLabel: "Course recommender", guideName: "Course guide", guideState: "Ready to help · Academic year 2026/2027",
    welcome: "Hi! Describe your study programme and interests, and I will help you find a good starting point.", hint: "You can also mention level, ECTS, teaching period, or language.", examplesLabel: "Examples",
    suggestionPlan: "My study plan", suggestionPlanMeta: "Applied Mathematics · BSc", inputLabel: "Tell us what you are looking for in a course", placeholder: "E.g. I study MSc Computer Science and am interested in machine learning…", sendLabel: "Send message",
    disclaimer: "Recommendations are for guidance only. Always check the course description and prerequisites at DTU.", builtFrom: "Built with data from", courseDatabase: "DTU's course database", apiDocs: "API documentation",
    promptPlan: "I study Applied Mathematics and am unsure how the programme is structured and which courses are mandatory.", promptMachineLearning: "I study Computer Science and Engineering at MSc level and am looking for courses in machine learning.", promptOptimization: "I am a BSc student looking for a 5 ECTS course about optimization."
  },
  da: {
    title: "Kurskompas — find dit næste DTU-kursus", description: "Få personlige anbefalinger blandt officielle DTU-kurser.",
    brand: "Kurskompas", brandLabel: "Kurskompas forside", status: "Officielle DTU-data", languageLabel: "Vælg sprog", reset: "Ny samtale",
    eyebrow: "Din personlige kursusguide", heroTitle: "Fra interesse til<br><em>det rigtige kursus.</em>", heroCopy: "Fortæl hvad du læser, og hvad du gerne vil vide. Så forklarer vi din studieplan eller finder relevante kurser i DTU's officielle katalog.",
    chatLabel: "Kursusanbefaler", guideName: "Kursusguiden", guideState: "Klar til at hjælpe · Studieår 2026/2027",
    welcome: "Hej! Beskriv din studieretning og dine interesser, så finder jeg et godt udgangspunkt.", hint: "Du kan også nævne niveau, ECTS, periode eller undervisningssprog.", examplesLabel: "Eksempler",
    suggestionPlan: "Min studieplan", suggestionPlanMeta: "Anvendt Matematik · Bachelor", inputLabel: "Fortæl om dine kursusønsker", placeholder: "Fx: Jeg læser MSc Computer Science og interesserer mig for machine learning…", sendLabel: "Send besked",
    disclaimer: "Anbefalingerne er vejledende. Tjek altid kursusbeskrivelsen og forudsætningerne hos DTU.", builtFrom: "Bygget på data fra", courseDatabase: "DTU Kursusbasen", apiDocs: "API-dokumentation",
    promptPlan: "Jeg studerer Anvendt Matematik og er i tvivl om, hvordan studiet er opbygget, og hvilke kurser der er obligatoriske.", promptMachineLearning: "Jeg læser Computer Science and Engineering på MSc-niveau og søger kurser inden for machine learning.", promptOptimization: "Jeg er BSc-studerende og vil gerne finde et kursus på 5 ECTS om optimization."
  }
};

let currentLanguage = "en";

function setLanguage(language) {
  currentLanguage = language;
  const copy = translations[language];
  document.documentElement.lang = language;
  document.title = copy.title;
  document.querySelectorAll("[data-i18n]").forEach((element) => { element.textContent = copy[element.dataset.i18n]; });
  document.querySelectorAll("[data-i18n-html]").forEach((element) => { element.innerHTML = copy[element.dataset.i18nHtml]; });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => { element.setAttribute("aria-label", copy[element.dataset.i18nAriaLabel]); });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => { element.placeholder = copy[element.dataset.i18nPlaceholder]; });
  document.querySelectorAll("[data-i18n-content]").forEach((element) => { element.content = copy[element.dataset.i18nContent]; });
  document.querySelectorAll("[data-language]").forEach((button) => { button.setAttribute("aria-pressed", String(button.dataset.language === language)); });
}

document.querySelectorAll("[data-language]").forEach((button) => {
  button.addEventListener("click", () => setLanguage(button.dataset.language));
});

let messages = [];
let busy = false;

function scrollToLatest() {
  requestAnimationFrame(() => {
    conversation.scrollTop = conversation.scrollHeight;
  });
}

function resizeInput() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 150)}px`;
}

function addMessage(role, text) {
  const row = document.createElement("article");
  row.className = `message-row ${role === "user" ? "user-row" : "assistant-row"}`;

  if (role === "assistant") {
    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = "K";
    row.append(avatar);
  }

  const message = document.createElement("div");
  message.className = `message ${role === "user" ? "user-message" : "assistant-message"}`;
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  message.append(paragraph);
  row.append(message);
  conversation.append(row);
  scrollToLatest();
  return row;
}

function addTyping() {
  const row = document.createElement("article");
  row.className = "message-row assistant-row";
  row.id = "typingRow";
  row.innerHTML = '<div class="message-avatar" aria-hidden="true">K</div><div class="message assistant-message typing" aria-label="Finder kurser"><i></i><i></i><i></i></div>';
  conversation.append(row);
  scrollToLatest();
}

function addContextTags(context) {
  const values = [context.program, context.topic, context.level, context.ects ? `${context.ects} ECTS` : null, context.language, context.period].filter(Boolean);
  if (!values.length) return;
  const tags = document.createElement("div");
  tags.className = "context-tags";
  values.forEach((value) => {
    const tag = document.createElement("span");
    tag.textContent = value;
    tags.append(tag);
  });
  conversation.append(tags);
}

function studyCourseLabel(course) {
  const number = course.courseNumber ? `${course.courseNumber} · ` : "";
  const ectsValues = course.ectsOptions?.length > 1 ? course.ectsOptions.join("/") : course.ects;
  const ects = ectsValues ? ` (${ectsValues} ECTS)` : "";
  return `${number}${course.title}${ects}`;
}

function commonCourseEcts(courses) {
  const values = [...new Set(courses.map((course) => course.ects).filter((value) => value != null))];
  return values.length === 1 ? values[0] : null;
}

function studyRuleDescription(rule) {
  const ects = commonCourseEcts(rule.courses);
  const ectsPhrase = ects == null ? "" : ` på ${ects} ECTS`;

  if (rule.requirementType === "one_of") {
    const alternativeMatch = rule.description.match(/alternative to\s+([0-9/\s]+)/i);
    if (alternativeMatch) {
      const primaryNumbers = alternativeMatch[1].match(/\d{5}/g) || [];
      const alternativeNumbers = rule.courses
        .map((course) => course.courseNumber)
        .filter((number) => number && !primaryNumbers.includes(number));
      return (
        `Vælg ét kursus${ectsPhrase}. Normalt vælges ét af ${primaryNumbers.join(", ")}. ` +
        `Hvis du har avancerede innovationskompetencer, kan du i stedet vælge ét af ${alternativeNumbers.join(", ")}.`
      );
    }
    return `Vælg ét kursus${ectsPhrase} blandt mulighederne nedenfor.`;
  }
  if (rule.requirementType === "exact_count" && rule.requiredCount != null) {
    return `Vælg præcis ${rule.requiredCount} kurser blandt mulighederne nedenfor.`;
  }
  if (rule.requirementType === "min_count" && rule.requiredCount != null) {
    return `Vælg mindst ${rule.requiredCount} kurser blandt mulighederne nedenfor.`;
  }
  if (rule.requirementType === "group_ects" && rule.requiredEcts != null) {
    return `Vælg ${rule.requiredEcts} ECTS fra puljen nedenfor.`;
  }
  if (rule.requirementType === "remainder_pool") {
    return `De resterende ECTS i den programspecifikke blok vælges fra puljen nedenfor (${rule.courses.length} kurser).`;
  }
  return rule.description;
}

function sectionEctsSummary(section) {
  const opening = section.description?.slice(0, section.name.length + 80) || "";
  const match = opening.match(/\((\d+(?:[.,]\d+)?)\s*ECTS(?:\s*points?)?\)/i);
  return match ? `Krav for denne blok: ${match[1].replace(",", ".")} ECTS i alt.` : null;
}

function addStudyPlan(plan) {
  if (!plan) return;
  const overview = document.createElement("section");
  overview.className = "study-plan";
  overview.setAttribute("aria-label", `Studieplan for ${plan.programName}`);

  const heading = document.createElement("div");
  heading.className = "study-plan-head";
  const title = document.createElement("h2");
  title.textContent = plan.programName;
  const meta = document.createElement("span");
  meta.textContent = plan.validFromYear ? `${plan.degreeType} · Optag fra ${plan.validFromYear}` : plan.degreeType;
  heading.append(title, meta);
  overview.append(heading);

  plan.sections.forEach((section) => {
    const card = document.createElement("article");
    card.className = "study-plan-section";
    const sectionTitle = document.createElement("h3");
    sectionTitle.textContent = section.name;
    card.append(sectionTitle);

    const ectsSummary = sectionEctsSummary(section);
    if (ectsSummary) {
      const summary = document.createElement("p");
      summary.className = "study-plan-label";
      summary.textContent = ectsSummary;
      card.append(summary);
    }

    const mandatory = section.courses.filter((course) => course.requirementRole === "mandatory");
    if (mandatory.length) {
      const label = document.createElement("p");
      label.className = "study-plan-label";
      label.textContent = "Obligatoriske kurser";
      const list = document.createElement("ul");
      mandatory.forEach((course) => {
        const item = document.createElement("li");
        item.textContent = studyCourseLabel(course);
        list.append(item);
      });
      card.append(label, list);
    }

    const seenUnlinkedDescriptions = new Set();
    section.requirements.filter((rule) => rule.requirementType !== "all_of").forEach((rule) => {
      const descriptionKey = rule.description.trim().replace(/\s+/g, " ").toLowerCase();
      if (!rule.courses.length && seenUnlinkedDescriptions.has(descriptionKey)) return;
      if (!rule.courses.length) seenUnlinkedDescriptions.add(descriptionKey);

      const block = document.createElement("div");
      block.className = `study-plan-rule${rule.isSubrequirement ? " subrule" : ""}`;
      const description = document.createElement("p");
      description.textContent = studyRuleDescription(rule);
      block.append(description);
      if (rule.courses.length) {
        const choices = document.createElement("p");
        choices.className = "study-plan-choices";
        choices.textContent = rule.courses.map(studyCourseLabel).join(" · ");
        block.append(choices);
      }
      card.append(block);
    });

    if (["projekter", "projects"].includes(section.name.toLowerCase())) {
      const projects = document.createElement("p");
      projects.className = "study-plan-choices";
      projects.textContent = section.courses.map(studyCourseLabel).join(" · ");
      card.append(projects);
    }
    const sectionName = section.name.toLowerCase();
    if (sectionName === "forhåndsgodkendte kandidatkurser" || (sectionName.includes("pre-approved") && sectionName.includes("msc"))) {
      const count = document.createElement("p");
      count.textContent = `${section.courses.length} forhåndsgodkendte kandidatkurser i den importerede studieplan.`;
      card.append(count);
    }
    overview.append(card);
  });

  const url = safeSourceUrl(plan.sourceUrl);
  if (url) {
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = "Se den officielle studieplan hos DTU ↗";
    overview.append(link);
  }
  conversation.append(overview);
  scrollToLatest();
}

function specializationCourseLabel(course) {
  const number = course.courseNumber ? `${course.courseNumber} · ` : "";
  const ects = course.ects != null ? ` (${course.ects} ECTS)` : "";
  const historical = course.isTerminated ? " · udgået" : "";
  return `${number}${course.title}${ects}${historical}`;
}

function specializationRuleDescription(rule) {
  if (rule.requirementType === "min_ects" && rule.requiredEcts != null) {
    return `Vælg mindst ${rule.requiredEcts} ECTS fra denne kursuspulje.`;
  }
  if (rule.requirementType === "one_of") return "Vælg ét af kurserne nedenfor.";
  if (rule.requirementType === "min_count" && rule.requiredCount != null) {
    return `Vælg mindst ${rule.requiredCount} kurser fra denne gruppe.`;
  }
  if (rule.requirementType === "all_of") return "Alle kurserne nedenfor er obligatoriske.";
  if (rule.requirementType === "recommended") return "Anbefalede kurser, som ikke er obligatoriske.";
  if (rule.requirementType === "historical") return "Udgåede kurser, som DTU angiver stadig tæller.";
  return rule.description;
}

function addSpecializations(specializations) {
  if (!specializations?.length) return;
  const overview = document.createElement("section");
  overview.className = "study-plan";
  overview.setAttribute("aria-label", `Specialiseringer for ${specializations[0].programName}`);

  const heading = document.createElement("div");
  heading.className = "study-plan-head";
  const title = document.createElement("h2");
  title.textContent = `Specialiseringer · ${specializations[0].programName}`;
  heading.append(title);
  overview.append(heading);

  specializations.forEach((specialization) => {
    const card = document.createElement("article");
    card.className = "study-plan-section";
    const name = document.createElement("h3");
    name.textContent = specialization.name;
    card.append(name);
    if (specialization.description) {
      const description = document.createElement("p");
      description.textContent = specialization.description;
      card.append(description);
    }
    specialization.requirements.forEach((rule) => {
      const block = document.createElement("div");
      block.className = "study-plan-rule";
      const description = document.createElement("p");
      description.textContent = specializationRuleDescription(rule);
      block.append(description);
      if (rule.courses.length) {
        const choices = document.createElement("p");
        choices.className = "study-plan-choices";
        choices.textContent = rule.courses.map(specializationCourseLabel).join(" · ");
        block.append(choices);
      }
      card.append(block);
    });
    const url = safeSourceUrl(specialization.sourceUrl);
    if (url) {
      const link = document.createElement("a");
      link.href = url;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = "Se specialiseringen hos DTU ↗";
      card.append(link);
    }
    overview.append(card);
  });
  conversation.append(overview);
  scrollToLatest();
}

function safeSourceUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname.endsWith("dtu.dk") ? url.href : null;
  } catch {
    return null;
  }
}

function addRecommendations(courses) {
  if (!courses.length) return;
  const list = document.createElement("section");
  list.className = "recommendations";
  list.setAttribute("aria-label", "Anbefalede kurser");

  courses.forEach((course) => {
    const card = document.createElement("article");
    card.className = "course-card";

    const head = document.createElement("div");
    head.className = "course-card-head";
    const number = document.createElement("span");
    number.className = "course-number";
    number.textContent = course.courseNumber;
    const ects = document.createElement("span");
    ects.className = "course-ects";
    ects.textContent = course.ects ? `${course.ects} ECTS` : "ECTS ikke angivet";
    head.append(number, ects);

    const title = document.createElement("h2");
    title.textContent = course.title;

    const meta = document.createElement("div");
    meta.className = "course-meta";
    [course.level, course.period, course.schedule, course.language].filter(Boolean).forEach((value) => {
      const item = document.createElement("span");
      item.textContent = value;
      meta.append(item);
    });

    card.append(head, title, meta);
    if (course.description) {
      const description = document.createElement("p");
      description.className = "course-description";
      description.textContent = course.description;
      card.append(description);
    }
    const reason = document.createElement("p");
    reason.className = "course-reason";
    reason.textContent = course.reason;
    card.append(reason);

    const url = safeSourceUrl(course.sourceUrl);
    if (url) {
      const link = document.createElement("a");
      link.href = url;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = "Se hos DTU ↗";
      card.append(link);
    }
    list.append(card);
  });
  conversation.append(list);
  scrollToLatest();
}

async function submitMessage(text) {
  const cleaned = text.trim();
  if (!cleaned || busy) return;
  busy = true;
  sendButton.disabled = true;
  suggestions?.remove();
  messages.push({ role: "user", content: cleaned });
  addMessage("user", cleaned);
  input.value = "";
  resizeInput();
  addTyping();

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: messages.slice(-12), academicYear: "2026-2027" }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result = await response.json();
    document.querySelector("#typingRow")?.remove();
    messages.push({ role: "assistant", content: result.reply });
    addMessage("assistant", result.reply);
    addContextTags(result.understood);
    addStudyPlan(result.studyPlan);
    addSpecializations(result.specializations);
    addRecommendations(result.recommendations);
  } catch (error) {
    document.querySelector("#typingRow")?.remove();
    addMessage("assistant", "Der opstod en fejl, mens jeg søgte. Prøv igen om et øjeblik.");
    console.error(error);
  } finally {
    busy = false;
    sendButton.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  submitMessage(input.value);
});

input.addEventListener("input", resizeInput);
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

document.querySelectorAll("[data-prompt-key]").forEach((button) => {
  button.addEventListener("click", () => submitMessage(translations[currentLanguage][button.dataset.promptKey]));
});

resetButton.addEventListener("click", () => window.location.reload());
