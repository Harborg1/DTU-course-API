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
  const values = [context.topic, context.level, context.ects ? `${context.ects} ECTS` : null, context.language, context.period].filter(Boolean);
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

