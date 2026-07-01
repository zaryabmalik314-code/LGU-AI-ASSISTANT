// ---------------------------------------------------------------------------
// LGU AI Mentor — video-driven front end for /recommend/eligible
// ---------------------------------------------------------------------------

// "Waiting for response" loop — plays whenever the mentor has asked a
// question and is holding for the student's answer. Crossfades in after
// every question clip, and seamlessly re-loops itself for as long as needed.
// ---------------------------------------------------------------------------
// TEMPORARY DIAGNOSTICS — flip to false once the interests-step issue is
// confirmed fixed. Logs every step transition and clip lifecycle event to
// the console so we can see exactly which step/clip actually runs, instead
// of guessing from code alone.
// ---------------------------------------------------------------------------
const DEBUG_STEPS = true;
function dbg(...args) {
  if (DEBUG_STEPS) console.log("[mentor]", ...args);
}

const IDLE_CLIP = "Mentor_waiting_for_student_response_202607010417.mp4";

// Both the CSS opacity transition (--crossfade-ms in style.css) and the JS
// pause/cleanup timer below are driven off this single constant so the two
// can never drift out of sync.
const CROSSFADE_MS = 400;

// How long before the idle clip's own ending to start crossfading back into
// a fresh copy of itself, so a multi-minute wait never shows a hard loop cut.
const IDLE_LOOP_LEAD = 0.45;

const videoA = document.getElementById("video-a");
const videoB = document.getElementById("video-b");
const overlayEl = document.getElementById("overlay");
const overlayInner = document.getElementById("overlay-inner");
const resultsEl = document.getElementById("results");
const progressEl = document.getElementById("progress");
const progressLabel = document.getElementById("progress-label");
const progressFill = document.getElementById("progress-fill");

let frontIsA = true;
const getFront = () => (frontIsA ? videoA : videoB);
const getBack = () => (frontIsA ? videoB : videoA);

function crossfadeToBack() {
  const back = getBack();
  const front = getFront();
  back.classList.add("active");
  front.classList.remove("active");
  frontIsA = !frontIsA;
  setTimeout(() => front.pause(), CROSSFADE_MS + 80);
}

// Every call to playClip() bumps this token. Any callback (timeupdate/ended)
// captured by an earlier call checks its own token against the current one
// before acting, so a clip that gets interrupted (e.g. the idle loop, cut
// short by the user clicking Continue) can't fire stale work.
let playToken = 0;

/**
 * Loads `file` into the hidden video layer and crossfades it to the front
 * the moment it's ready to play.
 *
 * opts.loop        - native loop attribute (not used for the idle clip —
 *                     that uses leadOut/onLeadOut instead, for a seamless
 *                     crossfaded loop rather than a hard cut)
 * opts.revealAt     - seconds into the clip at which onReveal fires. Generic
 *                     hook — callers decide what it means for a given clip
 *                     (e.g. "the question has finished being asked").
 * opts.onReveal     - called once, at revealAt
 * opts.leadOut      - seconds before the clip ends at which onLeadOut fires
 * opts.onLeadOut    - called once, at duration - leadOut
 * opts.onEnded      - called when the clip finishes
 */
function playClip(file, { loop = false, revealAt = null, onReveal = null, leadOut = null, onLeadOut = null, onEnded = null } = {}) {
  const myToken = ++playToken;
  const back = getBack();

  back.oncanplay = null;
  back.ontimeupdate = null;
  back.onended = null;

  back.loop = loop;
  back.muted = loop;

  let revealed = false;
  let leadOutFired = false;

  back.oncanplay = () => {
    if (myToken !== playToken) return;
    dbg("canplay:", file, "duration:", back.duration);
    back.oncanplay = null;
    const p = back.play();
    if (p && p.catch) {
      p.catch((err) => {
        dbg("play() rejected for", file, err);
        back.muted = true;
        back.play();
      });
    }
    crossfadeToBack();
  };

  if (onReveal && revealAt != null) {
    back.ontimeupdate = () => {
      if (myToken !== playToken) return;
      if (!revealed && back.currentTime >= revealAt) {
        revealed = true;
        dbg("onReveal fired for", file, "at", back.currentTime.toFixed(2) + "s (revealAt:", revealAt + ")");
        onReveal();
      }
      if (onLeadOut && leadOut != null && !leadOutFired && back.duration && back.duration - back.currentTime <= leadOut) {
        leadOutFired = true;
        onLeadOut();
      }
    };
  } else if (onLeadOut && leadOut != null) {
    back.ontimeupdate = () => {
      if (myToken !== playToken) return;
      if (!leadOutFired && back.duration && back.duration - back.currentTime <= leadOut) {
        leadOutFired = true;
        onLeadOut();
      }
    };
  }

  if (onEnded) {
    back.onended = () => {
      if (myToken !== playToken) return;
      dbg("ended:", file);
      onEnded();
    };
  }

  back.onerror = () => {
    if (myToken !== playToken) return;
    dbg("ERROR loading/playing:", file, back.error);
  };

  back.src = `/static/videos/${file}`;
  dbg("loading:", file);
  return back;
}

// Keeps the mentor "alive" indefinitely: each cycle crossfades into a fresh
// copy of the idle clip slightly before the current one ends, so there's
// never a hard loop cut no matter how long the student takes to answer.
function goIdle() {
  playClip(IDLE_CLIP, {
    leadOut: IDLE_LOOP_LEAD,
    onLeadOut: () => goIdle(),
  });
}

// ---------------------------------------------------------------------------
// Overlay show/hide (slide-up while mentor is still speaking)
// ---------------------------------------------------------------------------

function showOverlay(renderFn) {
  overlayInner.innerHTML = "";
  renderFn();
  overlayEl.classList.add("active");
  // next frame so the transition actually animates
  requestAnimationFrame(() => overlayInner.classList.add("visible"));
}

function hideOverlay() {
  overlayInner.classList.remove("visible");
  overlayEl.classList.remove("active");
}

function flash(el) {
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 500);
}

// ---------------------------------------------------------------------------
// Conversational pacing
//
// OPTIONS_REVEAL_DELAY_MS: the beat of silence after the mentor finishes
// asking a question and before the answer options animate in. Keeps the
// interaction feeling like a conversation (listen, pause, then respond)
// instead of a form where every control is visible at once.
//
// ACK_DISPLAY_MS / ACK_MESSAGES: once the student picks an answer, we show a
// short acknowledgment in place of the controls for this long before moving
// on to the next mentor clip.
// ---------------------------------------------------------------------------

const OPTIONS_REVEAL_DELAY_MS = 600; // within the requested 0.5-1s conversational pause
const ACK_DISPLAY_MS = 550; // within the requested 400-700ms acknowledgment window
const ACK_MESSAGES = ["Great!", "Perfect.", "Got it.", "Excellent choice."];

// Swaps the current field-controls for a brief acknowledgment message, then
// calls onDone (which is what actually advances to the next question) after
// ACK_DISPLAY_MS. Used by every render*Step below instead of calling onDone
// straight away, so selecting an answer never jumps directly into the next
// clip with no feedback.
function acknowledgeThen(onDone) {
  const message = ACK_MESSAGES[Math.floor(Math.random() * ACK_MESSAGES.length)];
  overlayInner.innerHTML = `<div class="ack-message">${message}</div>`;
  requestAnimationFrame(() => {
    const ackEl = overlayInner.querySelector(".ack-message");
    if (ackEl) ackEl.classList.add("shown");
  });
  setTimeout(onDone, ACK_DISPLAY_MS);
}

// ---------------------------------------------------------------------------
// Progress indicator ("Question N of M")
//
// One clip = one question. 5 input questions total: Matric %, Stream,
// Intermediate %, Interests, Career Goals — each tied to its own mentor
// clip, its own revealAt, and its own overlay.
// ---------------------------------------------------------------------------

const TOTAL_QUESTIONS = 5;

function showProgress(current) {
  progressLabel.textContent = `Question ${current} of ${TOTAL_QUESTIONS}`;
  progressFill.style.width = `${(current / TOTAL_QUESTIONS) * 100}%`;
  progressEl.classList.remove("hidden");
  requestAnimationFrame(() => progressEl.classList.add("visible"));
}

function hideProgress() {
  progressEl.classList.remove("visible");
}

// ---------------------------------------------------------------------------
// Collected answers sent to the backend
// ---------------------------------------------------------------------------

const profile = {
  matric_pct: null,
  inter_pct: null,
  inter_stream: "",
  // No dedicated clip/question for this in the current one-clip-per-question
  // flow — kept as an empty array so the /recommend/eligible payload shape
  // is unchanged. Only matters if an admission rule specifies required
  // subjects; re-add a step (and a clip) if that turns out to matter.
  subjects: [],
  interests: [],
  career_goals: []
};

// ---------------------------------------------------------------------------
// Step definitions — one mentor clip = one question = one overlay = one
// idle loop while we wait, then Continue moves to the next clip. No step
// bundles more than one question anymore.
//
// revealAt values are tuned from the actual speech in each clip (via
// silence-gap analysis: a short filler beat, then the real question — see
// IDLE_LOOP_LEAD comment above for the crossfade side of this), NOT a flat
// "N seconds before the end". If a clip gets re-recorded, these need
// re-checking against the new audio.
//
// IMPORTANT — asset note: there are no clips individually recorded/named
// for "Matric %" or "Stream" yet. This project only ships 8 non-idle clips
// total, which happens to match the 8-step sequence 1:1, so the two generic
// "Continue_seamlessly…" / "Reference_Assets…" clips (previously played as
// silent filler with no question at all) are repurposed below as the Matric
// % and Stream questions. Their revealAt values are estimated from silence
// gaps only — nobody here has confirmed what's actually said in them, so
// re-check both against the real audio and adjust revealAt (and swap the
// files if they turn out to be mislabeled) once you've reviewed them.
// ---------------------------------------------------------------------------

const STEPS = [
  { id: "welcome", file: "AI_mentor_welcomes_students_202607010230.mp4", type: "auto" },
  { id: "introduction", file: "Continue_seamlessly_from_the_uploaded_202607010230.mp4", type: "auto" },

  // NEEDS VERIFICATION — see asset note above.
  // speechEndAt is null for now — the ~2s "slow" pop-up you're seeing is
  // very likely trailing silent footage in this clip after the mentor
  // actually finishes asking the question, so options wait for onEnded
  // (full file length) instead of the real speech end. Fix: open this
  // file in any video player, find the timestamp (in seconds) where the
  // voice audibly stops, and set speechEndAt to that number. Once set,
  // options will pop up ~0.6s after that point instead of after the
  // whole clip (including the dead air) finishes.
  { id: "matric", file: "Continue_seamlessly_from_the_uploaded_202607010230__1_.mp4", type: "input", revealAt: 2.2, speechEndAt: null, revealLeadOut: 2, progressStart: 1, render: renderMatricStep },

  // NEEDS VERIFICATION — see asset note above. Same speechEndAt fix as above.
  { id: "stream", file: "Reference_Assets__Previous_video__continuity_202607010230.mp4", type: "input", revealAt: 1.1, speechEndAt: null, revealLeadOut: 2, progressStart: 2, render: renderStreamStep },

  // Same speechEndAt fix as above.
  { id: "interPct", file: "Mentor_asks_intermediate_percentage_202607010230.mp4", type: "input", revealAt: 2.6, speechEndAt: null, revealLeadOut: 2, progressStart: 3, render: renderInterPctStep },
  { id: "interests", file: "Mentor_asks_about_interests_202607010230.mp4", type: "input", revealAt: 1.2, speechEndAt: null, progressStart: 4, render: renderInterestsStep },
  { id: "career", file: "Mentor_asks_career_goals_question_202607010230.mp4", type: "input", revealAt: 2.9, speechEndAt: null, progressStart: 5, render: renderCareerStep },
  { id: "analyzing", file: "Mentor_analyzes_profile_in_library_202607010230.mp4", type: "analyze" }
];

let stepIndex = 0;
let waitingForAnalysis = false;

function playStep(index) {
  if (index >= STEPS.length) return;
  stepIndex = index;
  const step = STEPS[index];
  dbg(`playStep(${index}) -> step "${step.id}" (${step.type}), file: ${step.file || "n/a"}`);
  hideOverlay();

  if (step.type === "auto") {
    hideProgress();
    playClip(step.file, { onEnded: () => playStep(index + 1) });
    return;
  }

  if (step.type === "input") {
    // Reveal as soon as the mentor actually finishes SPEAKING, not when the
    // video FILE ends. Priority order:
    //   1. step.speechEndAt (exact second, once you've checked the footage)
    //   2. step.revealLeadOut (reveal N seconds before the clip's natural
    //      end — a rough fix for trailing dead footage when we don't have
    //      an exact timestamp yet)
    //   3. onEnded (safety net — always fires eventually regardless)
    let revealed = false;
    const reveal = () => {
      if (revealed) return;
      revealed = true;
      goIdle();
      showProgress(step.progressStart);
      showOverlay(() => step.render(() => advanceFromInput(index), step.progressStart));
    };
    playClip(step.file, {
      revealAt: step.speechEndAt,
      onReveal: step.speechEndAt != null ? reveal : null,
      leadOut: step.speechEndAt == null ? step.revealLeadOut : null,
      onLeadOut: (step.speechEndAt == null && step.revealLeadOut != null) ? reveal : null,
      onEnded: reveal // safety net either way
    });
    return;
  }

  if (step.type === "analyze") {
    hideProgress();
    waitingForAnalysis = false;
    runRecommendation();
    playClip(step.file, {
      onEnded: () => {
        if (recommendationSettled) {
          showResults();
        } else {
          waitingForAnalysis = true;
          goIdle();
          showAnalyzingSpinner();
        }
      }
    });
  }
}

function advanceFromInput(index) {
  dbg(`advanceFromInput(${index}) -> next index ${index + 1}`);
  // Crossfade into the next clip right away — no waiting on the overlay's
  // own hide animation, which plays out concurrently — so clicking Continue
  // feels like the mentor picking the conversation back up immediately.
  hideOverlay();
  playStep(index + 1);
}

// ---------------------------------------------------------------------------
// Step renderers
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Single-question step renderers — Matric %, Stream, and Intermediate %
// each get their own clip, own overlay, and own field-card. No chaining
// between them: each one calls onDone() exactly once, which is what
// advances to the *next clip* (see advanceFromInput).
// ---------------------------------------------------------------------------

// Mounts a single field-card into the (already-cleared) overlay and
// triggers its entrance transition. Used by every one-question step below.
function mountField(card) {
  overlayInner.appendChild(card);
  requestAnimationFrame(() => card.classList.add("shown"));

  // The field-title inside `card` is visible as soon as the card slides in
  // above; the interactive part (wrapped in .field-controls by
  // buildSliderCard/buildChipCard) stays hidden and unclickable until this
  // fires, giving the "mentor finishes speaking → pause → options appear"
  // beat requested.
  const controls = card.querySelector(".field-controls");
  if (controls) {
    setTimeout(() => controls.classList.add("shown"), OPTIONS_REVEAL_DELAY_MS);
  }
}

function renderMatricStep(onDone) {
  mountField(buildSliderCard({
    title: "What was your Matric percentage?",
    initial: 75,
    buttonLabel: "Continue",
    onNext: (v) => {
      profile.matric_pct = v;
      acknowledgeThen(onDone);
    }
  }));
}

function renderStreamStep(onDone) {
  const streams = ["Pre-Engineering", "Pre-Medical", "ICS", "Commerce", "Arts", "Other"];
  mountField(buildChipCard({
    title: "Which Intermediate stream did you study?",
    options: streams,
    multi: false,
    buttonLabel: "Continue",
    requireSelection: true,
    onNext: (val) => {
      profile.inter_stream = val;
      acknowledgeThen(onDone);
    }
  }));
}

function renderInterPctStep(onDone) {
  mountField(buildSliderCard({
    title: "And your Intermediate percentage?",
    initial: 75,
    buttonLabel: "Continue",
    onNext: (v) => {
      profile.inter_pct = v;
      acknowledgeThen(onDone);
    }
  }));
}

// Slider field card — used for both percentage questions. The slider/value/
// button are wrapped in .field-controls so mountField() can reveal them
// after the pause, separately from the field-title above them.
function buildSliderCard({ title, initial, buttonLabel, onNext }) {
  const card = document.createElement("div");
  card.className = "field-card";
  card.innerHTML = `
    <div class="field-title">${title}</div>
    <div class="field-controls">
      <div class="slider-row">
        <span class="slider-edge">0</span>
        <input type="range" min="0" max="100" step="1" value="${initial}" class="pct-slider">
        <span class="slider-edge">100</span>
      </div>
      <div class="slider-value">${initial}%</div>
      <button class="btn" type="button">${buttonLabel}</button>
    </div>
  `;

  const slider = card.querySelector(".pct-slider");
  const valueEl = card.querySelector(".slider-value");
  slider.addEventListener("input", () => {
    valueEl.textContent = `${slider.value}%`;
  });

  card.querySelector(".btn").addEventListener("click", () => {
    onNext(parseInt(slider.value, 10));
  });

  return card;
}

// Chip field card — single-select (Stream) or multi-select (Subjects), no
// free-text entry. requireSelection gates the button until something's picked.
function buildChipCard({ title, options, multi, buttonLabel, requireSelection, onNext }) {
  const card = document.createElement("div");
  card.className = "field-card";
  card.innerHTML = `
    <div class="field-title">${title}</div>
    <div class="field-controls">
      <div class="chip-row"></div>
      <button class="btn" type="button" ${requireSelection ? "disabled" : ""}>${buttonLabel}</button>
    </div>
  `;

  const chipRow = card.querySelector(".chip-row");
  const button = card.querySelector(".btn");
  const selected = new Set();

  options.forEach(label => {
    const chip = document.createElement("div");
    chip.className = "chip";
    chip.textContent = label;
    chip.addEventListener("click", () => {
      if (multi) {
        if (selected.has(label)) {
          selected.delete(label);
          chip.classList.remove("selected");
        } else {
          selected.add(label);
          chip.classList.add("selected");
        }
      } else {
        selected.clear();
        selected.add(label);
        [...chipRow.children].forEach(c => c.classList.remove("selected"));
        chip.classList.add("selected");
      }
      if (requireSelection) button.disabled = selected.size === 0;
    });
    chipRow.appendChild(chip);
  });

  button.addEventListener("click", () => {
    if (requireSelection && selected.size === 0) return flash(chipRow);
    onNext(multi ? Array.from(selected) : [...selected][0]);
  });

  return card;
}

function renderInterestsStep(onDone) {
  const suggestions = [
    "Artificial Intelligence", "Web Development", "Cybersecurity",
    "Data Science", "Networking", "Graphic Design",
    "Business & Finance", "Robotics", "Game Development"
  ];
  renderChipStep({
    suggestions,
    placeholder: "Add your own interest…",
    onDone: (selected) => {
      profile.interests = selected;
      acknowledgeThen(onDone);
    }
  });
}

function renderCareerStep(onDone) {
  const suggestions = [
    "Software Engineer", "Data Scientist", "Entrepreneur",
    "Doctor", "Cybersecurity Analyst", "UI/UX Designer",
    "AI Researcher", "Network Engineer", "Business Analyst"
  ];
  renderChipStep({
    suggestions,
    placeholder: "Add your own goal…",
    onDone: (selected) => {
      profile.career_goals = selected;
      acknowledgeThen(onDone);
    }
  });
}

function renderChipStep({ suggestions, placeholder, onDone }) {
  const selected = new Set();

  // Same .field-controls treatment as buildSliderCard/buildChipCard: stays
  // hidden and unclickable until OPTIONS_REVEAL_DELAY_MS after this step
  // is mounted (i.e. after the mentor finishes asking the question).
  overlayInner.innerHTML = `
    <div class="field-controls">
      <div class="chip-row" id="chip-row"></div>
      <div class="field-row">
        <input type="text" id="custom-input" placeholder="${placeholder}">
        <button class="btn btn-secondary" id="add-btn">Add</button>
      </div>
      <button class="btn" id="continue-btn" disabled>Continue</button>
    </div>
  `;

  const controls = overlayInner.querySelector(".field-controls");
  setTimeout(() => controls.classList.add("shown"), OPTIONS_REVEAL_DELAY_MS);

  const chipRow = document.getElementById("chip-row");
  const customInput = document.getElementById("custom-input");
  const addBtn = document.getElementById("add-btn");
  const continueBtn = document.getElementById("continue-btn");

  function addChip(label) {
    if (!label || selected.has(label)) return;
    const chip = document.createElement("div");
    chip.className = "chip selected";
    chip.textContent = label;
    chip.addEventListener("click", () => {
      selected.delete(label);
      chip.remove();
      continueBtn.disabled = selected.size === 0;
    });
    chipRow.appendChild(chip);
    selected.add(label);
    continueBtn.disabled = false;
  }

  suggestions.forEach(label => {
    const chip = document.createElement("div");
    chip.className = "chip";
    chip.textContent = label;
    chip.addEventListener("click", () => {
      if (selected.has(label)) return;
      chip.classList.add("selected");
      chip.style.pointerEvents = "none";
      selected.add(label);
      continueBtn.disabled = false;
    });
    chipRow.appendChild(chip);
  });

  addBtn.addEventListener("click", () => {
    const val = customInput.value.trim();
    if (val) {
      addChip(val);
      customInput.value = "";
    }
  });

  customInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addBtn.click();
    }
  });

  continueBtn.addEventListener("click", () => onDone(Array.from(selected)));
}

// ---------------------------------------------------------------------------
// Backend call
// ---------------------------------------------------------------------------

let recommendationSettled = false;
let recommendationData = null;
let recommendationError = null;

function runRecommendation() {
  recommendationSettled = false;
  recommendationData = null;
  recommendationError = null;

  fetch("/recommend/eligible", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile)
  })
    .then(async (res) => {
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody.detail || `Request failed (${res.status})`);
      }
      return res.json();
    })
    .then((data) => {
      recommendationData = data;
      recommendationSettled = true;
      if (waitingForAnalysis) showResults();
    })
    .catch((err) => {
      recommendationError = err.message || "Something went wrong.";
      recommendationSettled = true;
      if (waitingForAnalysis) showResults();
    });
}

function showAnalyzingSpinner() {
  showOverlay(() => {
    overlayInner.innerHTML = `
      <div class="spinner-box">
        <div class="spinner"></div>
        <div style="color:#fff; font-size:13px;">Analyzing your profile…</div>
      </div>
    `;
  });
}

function showResults() {
  hideOverlay();
  hideProgress();

  if (recommendationError) {
    resultsEl.innerHTML = `
      <h2>Something went wrong</h2>
      <div class="error-box">${escapeHtml(recommendationError)}</div>
    `;
  } else {
    const { eligible_programs = [], explanations = [] } = recommendationData || {};

    if (eligible_programs.length === 0) {
      resultsEl.innerHTML = `
        <h2>No matching programs found</h2>
        <p>Try adjusting your subjects, interests, or career goals.</p>
      `;
    } else {
      const explMap = {};
      explanations.forEach(e => { explMap[e.program_id] = e; });

      const cards = eligible_programs.map(p => {
        const e = explMap[p.program_id] || {};
        return `
          <div class="program-card">
            <h3>${escapeHtml(p.name)}</h3>
            <div class="meta">${escapeHtml(p.department || "")} · ${escapeHtml(String(p.duration_years || ""))} years</div>
            ${e.summary ? `<p>${escapeHtml(e.summary)}</p>` : ""}
            ${e.academic_compatibility ? `<p><span class="label">Academic fit:</span> ${escapeHtml(e.academic_compatibility)}</p>` : ""}
            ${e.interest_compatibility ? `<p><span class="label">Interest fit:</span> ${escapeHtml(e.interest_compatibility)}</p>` : ""}
            ${e.career_compatibility ? `<p><span class="label">Career fit:</span> ${escapeHtml(e.career_compatibility)}</p>` : ""}
            ${e.future_opportunities ? `<p><span class="label">Future opportunities:</span> ${escapeHtml(e.future_opportunities)}</p>` : ""}
          </div>
        `;
      }).join("");

      resultsEl.innerHTML = `<h2>Your recommended programs</h2>${cards}`;
    }
  }

  resultsEl.classList.remove("hidden");
  requestAnimationFrame(() => resultsEl.classList.add("visible"));
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// Kick off
playStep(0);