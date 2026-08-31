const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const sendButton = document.querySelector("#sendButton");
const conversation = document.querySelector("#conversation");
const resetButton = document.querySelector("#resetButton");
const suggestions = document.querySelector("#suggestions");
const howItWorksButton = document.querySelector("#howItWorksButton");
const howItWorksDialog = document.querySelector("#howItWorksDialog");

const translations = {
  en: {
    title: "Course Compass — find your next DTU course", description: "Get personal recommendations from DTU's official course catalogue.",
    brand: "Course Compass", brandLabel: "Course Compass home", status: "Official DTU data", languageLabel: "Choose language", reset: "New chat", howItWorks: "How it works",
    eyebrow: "Your personal course guide", heroTitle: "From curiosity to<br><em>the right course.</em>", heroCopy: "Tell us what you study and what you want to learn. We will explain your study plan or find relevant courses in DTU's official catalogue.",
    chatLabel: "Course recommender", guideName: "Course guide", guideState: "Ready to help · Academic year 2026/2027",
    welcome: "Hi! Describe your study programme and interests, and I will help you find a good starting point.", hint: "You can also mention level, ECTS, teaching period, or language.", examplesLabel: "Examples",
    suggestionPlan: "My study plan", suggestionPlanMeta: "Applied Mathematics · BSc", inputLabel: "Tell us what you are looking for in a course", placeholder: "E.g. I study MSc Computer Science and am interested in machine learning…", sendLabel: "Send message",
    disclaimer: "Recommendations are for guidance only. Always check the course description and prerequisites at DTU.", builtFrom: "Built with data from", courseDatabase: "DTU's course database", apiDocs: "API documentation",
    howEyebrow: "A quick guide", howTitle: "How Course Compass works", howCloseLabel: "Close guide", howIntro: "Ask in your own words. Include the study programme, course, or topic you mean, and add details such as level or ECTS when they matter.",
    howStepOneTitle: "Give context", howStepOneText: "Name your study programme, study level, or course number.", howStepTwoTitle: "Say what you need", howStepTwoText: "Ask for a study plan, comparison, specialization, or course recommendation.", howStepThreeTitle: "Refine the answer", howStepThreeText: "Follow up with constraints such as ECTS, teaching period, or subject.",
    howExamplesTitle: "Prompt templates", howExamplesHint: "Replace the text in angle brackets with your own details.", howUseTemplate: "Use template", howPromptCompare: "Compare <study programme 1> and <study programme 2>", howPromptPlan: "Show me the study plan for <study programme>", howPromptSpecializations: "Which specializations are available in <MSc programme>?", howPromptCourses: "Find <ECTS> ECTS courses about <topic> at <study level>", howPromptCourseDetails: "What are the prerequisites and exam format for course <course number>?", howNote: "Course Compass uses imported official DTU data. Always confirm final choices in DTU's current course and study information.",
    promptPlan: "I study Applied Mathematics and am unsure how the programme is structured and which courses are mandatory.", promptMachineLearning: "I study Computer Science and Engineering at MSc level and am looking for courses in machine learning.", promptOptimization: "I am a BSc student looking for a 5 ECTS course about optimization."
  },
  da: {
    title: "Kurskompas — find dit næste DTU-kursus", description: "Få personlige anbefalinger blandt officielle DTU-kurser.",
    brand: "Kurskompas", brandLabel: "Kurskompas forside", status: "Officielle DTU-data", languageLabel: "Vælg sprog", reset: "Ny samtale", howItWorks: "Sådan virker det",
    eyebrow: "Din personlige kursusguide", heroTitle: "Fra interesse til<br><em>det rigtige kursus.</em>", heroCopy: "Fortæl hvad du læser, og hvad du gerne vil vide. Så forklarer vi din studieplan eller finder relevante kurser i DTU's officielle katalog.",
    chatLabel: "Kursusanbefaler", guideName: "Kursusguiden", guideState: "Klar til at hjælpe · Studieår 2026/2027",
    welcome: "Hej! Beskriv din studieretning og dine interesser, så finder jeg et godt udgangspunkt.", hint: "Du kan også nævne niveau, ECTS, periode eller undervisningssprog.", examplesLabel: "Eksempler",
    suggestionPlan: "Min studieplan", suggestionPlanMeta: "Anvendt Matematik · Bachelor", inputLabel: "Fortæl om dine kursusønsker", placeholder: "Fx: Jeg læser MSc Computer Science og interesserer mig for machine learning…", sendLabel: "Send besked",
    disclaimer: "Anbefalingerne er vejledende. Tjek altid kursusbeskrivelsen og forudsætningerne hos DTU.", builtFrom: "Bygget på data fra", courseDatabase: "DTU Kursusbasen", apiDocs: "API-dokumentation",
    howEyebrow: "En hurtig guide", howTitle: "Sådan virker Kurskompas", howCloseLabel: "Luk guide", howIntro: "Spørg med dine egne ord. Nævn den studieretning, det kursus eller det emne, du mener, og tilføj oplysninger som niveau eller ECTS, når de er relevante.",
    howStepOneTitle: "Giv kontekst", howStepOneText: "Nævn din studieretning, dit studieniveau eller et kursusnummer.", howStepTwoTitle: "Fortæl, hvad du søger", howStepTwoText: "Spørg efter en studieplan, sammenligning, specialisering eller kursusanbefaling.", howStepThreeTitle: "Afgræns svaret", howStepThreeText: "Følg op med krav som ECTS, undervisningsperiode eller fagområde.",
    howExamplesTitle: "Promptskabeloner", howExamplesHint: "Erstat teksten i vinkelparenteser med dine egne oplysninger.", howUseTemplate: "Brug skabelon", howPromptCompare: "Sammenlign <studieretning 1> og <studieretning 2>", howPromptPlan: "Vis mig studieplanen for <studieretning>", howPromptSpecializations: "Hvilke specialiseringer findes på <kandidatretning>?", howPromptCourses: "Find kurser på <ECTS> ECTS om <emne> på <studieniveau>", howPromptCourseDetails: "Hvad er forudsætningerne og eksamensformen for kursus <kursusnummer>?", howNote: "Kurskompas bruger importerede officielle DTU-data. Bekræft altid dine endelige valg i DTU's aktuelle kursus- og studieinformation.",
    promptPlan: "Jeg studerer Anvendt Matematik og er i tvivl om, hvordan studiet er opbygget, og hvilke kurser der er obligatoriske.", promptMachineLearning: "Jeg læser Computer Science and Engineering på MSc-niveau og søger kurser inden for machine learning.", promptOptimization: "Jeg er BSc-studerende og vil gerne finde et kursus på 5 ECTS om optimization."
  }
};

const responseTranslations = {
  en: {
    studyPlanAria: (program) => `Study plan for ${program}`,
    admittedFrom: (year) => `Admission from ${year}`,
    blockRequirement: (ects) => `Requirement for this block: ${ects} ECTS in total.`,
    mandatoryCourses: "Mandatory courses",
    chooseOne: (ects) => `Choose one course${ects} from the options below.`,
    chooseAlternative: (ects, primary, alternatives) =>
      `Choose one course${ects}. Normally, choose one of ${primary}. ` +
      `If you have advanced innovation competencies, you may instead choose one of ${alternatives}.`,
    chooseExactCount: (count) => `Choose exactly ${count} courses from the options below.`,
    chooseMinimumCount: (count) => `Choose at least ${count} courses from the options below.`,
    chooseGroupEcts: (ects) => `Choose ${ects} ECTS from the pool below.`,
    remainderPool: (count) =>
      `Choose the remaining ECTS in the programme-specific block from the pool below (${count} courses).`,
    preapprovedCourses: (count) =>
      `${count} pre-approved MSc courses in the imported study plan.`,
    studyPlanLink: "View the official study plan at DTU ↗",
    specializationsAria: (program) => `Specializations for ${program}`,
    specializationsTitle: (program) => `Specializations · ${program}`,
    minimumSpecializationEcts: (ects) => `Choose at least ${ects} ECTS from this course pool.`,
    chooseOneSpecializationCourse: "Choose one of the courses below.",
    chooseMinimumSpecializationCourses: (count) => `Choose at least ${count} courses from this group.`,
    allSpecializationCourses: "All courses below are mandatory.",
    recommendedSpecializationCourses: "Recommended courses that are not mandatory.",
    historicalSpecializationCourses: "Discontinued courses that DTU states still count.",
    historicalCourseSuffix: " · discontinued",
    specializationLink: "View the specialization at DTU ↗",
  },
  da: {
    studyPlanAria: (program) => `Studieplan for ${program}`,
    admittedFrom: (year) => `Optag fra ${year}`,
    blockRequirement: (ects) => `Krav for denne blok: ${ects} ECTS i alt.`,
    mandatoryCourses: "Obligatoriske kurser",
    chooseOne: (ects) => `Vælg ét kursus${ects} blandt mulighederne nedenfor.`,
    chooseAlternative: (ects, primary, alternatives) =>
      `Vælg ét kursus${ects}. Normalt vælges ét af ${primary}. ` +
      `Hvis du har avancerede innovationskompetencer, kan du i stedet vælge ét af ${alternatives}.`,
    chooseExactCount: (count) => `Vælg præcis ${count} kurser blandt mulighederne nedenfor.`,
    chooseMinimumCount: (count) => `Vælg mindst ${count} kurser blandt mulighederne nedenfor.`,
    chooseGroupEcts: (ects) => `Vælg ${ects} ECTS fra puljen nedenfor.`,
    remainderPool: (count) =>
      `De resterende ECTS i den programspecifikke blok vælges fra puljen nedenfor (${count} kurser).`,
    preapprovedCourses: (count) =>
      `${count} forhåndsgodkendte kandidatkurser i den importerede studieplan.`,
    studyPlanLink: "Se den officielle studieplan hos DTU ↗",
    specializationsAria: (program) => `Specialiseringer for ${program}`,
    specializationsTitle: (program) => `Specialiseringer · ${program}`,
    minimumSpecializationEcts: (ects) => `Vælg mindst ${ects} ECTS fra denne kursuspulje.`,
    chooseOneSpecializationCourse: "Vælg ét af kurserne nedenfor.",
    chooseMinimumSpecializationCourses: (count) => `Vælg mindst ${count} kurser fra denne gruppe.`,
    allSpecializationCourses: "Alle kurserne nedenfor er obligatoriske.",
    recommendedSpecializationCourses: "Anbefalede kurser, som ikke er obligatoriske.",
    historicalSpecializationCourses: "Udgåede kurser, som DTU angiver stadig tæller.",
    historicalCourseSuffix: " · udgået",
    specializationLink: "Se specialiseringen hos DTU ↗",
  },
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

howItWorksButton.addEventListener("click", () => howItWorksDialog.showModal());

howItWorksDialog.addEventListener("click", (event) => {
  if (event.target === howItWorksDialog) howItWorksDialog.close();
});

document.querySelectorAll("[data-template-key]").forEach((button) => {
  button.addEventListener("click", () => {
    input.value = translations[currentLanguage][button.dataset.templateKey];
    resizeInput();
    howItWorksDialog.close();
    input.focus();
  });
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

function studyRuleDescription(rule, language) {
  const copy = responseTranslations[language];
  const ects = commonCourseEcts(rule.courses);
  const ectsPhrase = ects == null ? "" : language === "da" ? ` på ${ects} ECTS` : ` worth ${ects} ECTS`;

  if (rule.requirementType === "one_of") {
    const alternativeMatch = rule.description.match(/alternative to\s+([0-9/\s]+)/i);
    if (alternativeMatch) {
      const primaryNumbers = alternativeMatch[1].match(/\d{5}/g) || [];
      const alternativeNumbers = rule.courses
        .map((course) => course.courseNumber)
        .filter((number) => number && !primaryNumbers.includes(number));
      return copy.chooseAlternative(
        ectsPhrase,
        primaryNumbers.join(", "),
        alternativeNumbers.join(", "),
      );
    }
    return copy.chooseOne(ectsPhrase);
  }
  if (rule.requirementType === "exact_count" && rule.requiredCount != null) {
    return copy.chooseExactCount(rule.requiredCount);
  }
  if (rule.requirementType === "min_count" && rule.requiredCount != null) {
    return copy.chooseMinimumCount(rule.requiredCount);
  }
  if (rule.requirementType === "group_ects" && rule.requiredEcts != null) {
    return copy.chooseGroupEcts(rule.requiredEcts);
  }
  if (rule.requirementType === "remainder_pool") {
    return copy.remainderPool(rule.courses.length);
  }
  return rule.description;
}

function sectionEctsSummary(section, language) {
  const opening = section.description?.slice(0, section.name.length + 80) || "";
  const match = opening.match(/\((\d+(?:[.,]\d+)?)\s*ECTS(?:\s*points?)?\)/i);
  return match ? responseTranslations[language].blockRequirement(match[1].replace(",", ".")) : null;
}

function addStudyPlan(plan, language) {
  if (!plan) return;
  const copy = responseTranslations[language];
  const overview = document.createElement("section");
  overview.className = "study-plan";
  overview.setAttribute("aria-label", copy.studyPlanAria(plan.programName));

  const heading = document.createElement("div");
  heading.className = "study-plan-head";
  const title = document.createElement("h2");
  title.textContent = plan.programName;
  const meta = document.createElement("span");
  meta.textContent = plan.validFromYear
    ? `${plan.degreeType} · ${copy.admittedFrom(plan.validFromYear)}`
    : plan.degreeType;
  heading.append(title, meta);
  overview.append(heading);

  plan.sections.forEach((section) => {
    const card = document.createElement("article");
    card.className = "study-plan-section";
    const sectionTitle = document.createElement("h3");
    sectionTitle.textContent = section.name;
    card.append(sectionTitle);

    const ectsSummary = sectionEctsSummary(section, language);
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
      label.textContent = copy.mandatoryCourses;
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
      description.textContent = studyRuleDescription(rule, language);
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
      count.textContent = copy.preapprovedCourses(section.courses.length);
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
    link.textContent = copy.studyPlanLink;
    overview.append(link);
  }
  conversation.append(overview);
  scrollToLatest();
}

function specializationCourseLabel(course, language) {
  const number = course.courseNumber ? `${course.courseNumber} · ` : "";
  const ects = course.ects != null ? ` (${course.ects} ECTS)` : "";
  const historical = course.isTerminated ? responseTranslations[language].historicalCourseSuffix : "";
  return `${number}${course.title}${ects}${historical}`;
}

function specializationRuleDescription(rule, language) {
  const copy = responseTranslations[language];
  if (rule.requirementType === "min_ects" && rule.requiredEcts != null) {
    return copy.minimumSpecializationEcts(rule.requiredEcts);
  }
  if (rule.requirementType === "one_of") return copy.chooseOneSpecializationCourse;
  if (rule.requirementType === "min_count" && rule.requiredCount != null) {
    return copy.chooseMinimumSpecializationCourses(rule.requiredCount);
  }
  if (rule.requirementType === "all_of") return copy.allSpecializationCourses;
  if (rule.requirementType === "recommended") return copy.recommendedSpecializationCourses;
  if (rule.requirementType === "historical") return copy.historicalSpecializationCourses;
  return rule.description;
}

function addSpecializations(specializations, language) {
  if (!specializations?.length) return;
  const copy = responseTranslations[language];
  const overview = document.createElement("section");
  overview.className = "study-plan";
  overview.setAttribute("aria-label", copy.specializationsAria(specializations[0].programName));

  const heading = document.createElement("div");
  heading.className = "study-plan-head";
  const title = document.createElement("h2");
  title.textContent = copy.specializationsTitle(specializations[0].programName);
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
      description.textContent = specializationRuleDescription(rule, language);
      block.append(description);
      if (rule.courses.length) {
        const choices = document.createElement("p");
        choices.className = "study-plan-choices";
        choices.textContent = rule.courses.map((course) => specializationCourseLabel(course, language)).join(" · ");
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
      link.textContent = copy.specializationLink;
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
    // The API only uses user messages for conversational context. Assistant
    // replies can contain complete course lists and exceed the 800-character
    // input limit, so do not submit those replies again on the next turn.
    const requestMessages = messages
      .filter((message) => message.role === "user")
      .slice(-12);
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: requestMessages, academicYear: "2026-2027" }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result = await response.json();
    document.querySelector("#typingRow")?.remove();
    messages.push({ role: "assistant", content: result.reply });
    addMessage("assistant", result.reply);
    addContextTags(result.understood);
    const responseLanguage = result.responseLanguage || currentLanguage;
    addStudyPlan(result.studyPlan, responseLanguage);
    addSpecializations(result.specializations, responseLanguage);
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
