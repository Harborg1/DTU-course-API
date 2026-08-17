const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const sendButton = document.querySelector("#sendButton");
const conversation = document.querySelector("#conversation");
const resetButton = document.querySelector("#resetButton");
const suggestions = document.querySelector("#suggestions");

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

    section.requirements.filter((rule) => rule.requirementType !== "all_of").forEach((rule) => {
      const block = document.createElement("div");
      block.className = `study-plan-rule${rule.isSubrequirement ? " subrule" : ""}`;
      const description = document.createElement("p");
      description.textContent = rule.description;
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

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => submitMessage(button.dataset.prompt));
});

resetButton.addEventListener("click", () => window.location.reload());
