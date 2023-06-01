mapboxgl.accessToken = 'YOUR_ACCESS_TOKEN_HERE';

let mturkQueryString = window.location.href.slice(window.location.href.indexOf("?"));
let queryParams = new URLSearchParams(mturkQueryString);
let socket = io({ query: Object.fromEntries(queryParams.entries()) });
let player_id;
let practiceGame = true;
let originalTable;
let showBestSolution = false;
let playerTable;
let combinedTable;
let scale;
let proposal;
let proposalWithTravel;
let gameOver = false;
let audio;
let qualification_mode = false;
let events;
let role;
let feature_list;
let endGame;
import { map, getCyclingRoute, wrapCoords } from "./map.js";

const NUM_ROUNDS = 1;
const DEBUG = true;


socket.on("connect", function(data) {
  // Empty
});

socket.on("setup", function(data) {
  audio = new Audio(data["sound"]);
  qualification_mode = data["qualification_mode"];
  if (qualification_mode) {
    $("#game-title").html("<div>Worker Assignment Qualification Game</div>");
  }
});

socket.on("begin", function(data) {
  $("#instruction-overlay").prop("hidden", true);
  audio.play();

  // Prep the game
  $("#status").text("Starting game. Please reference the instructions if needed.");
  $(".actions").prop("hidden", true);
  player_id = data["player_id"];

  role = data["role"]
  if (role == "human") {
    setupHuman(data);
  } else if (role == "agent") {
    setupAgent(data);
  } else {
    console.error("unknown role ", data["role"]);
  }

  addEventToLog("Starting new game...");
});

socket.on("end_game", function(data) {
  disableInputs();
  gameOver = true;
  addEventToLog(`Your proposal had value ${parseInt(data["reward"])}, compared to randomly planning a travel itinerary, which gets a score of ${data["best_random_score"]}.`);
  if (!qualification_mode) {
    addEventToLog(`You earned a bonus of $${data["bonus"].toFixed(2)}.`);
    addEventToLog(`Please refresh the page to start a new game.`);
  } else {
    addEventToLog(`Thanks for playing our game! Please refresh the page to start a new game.`);
  }

  $(".waiting").prop("hidden", true);
  $("#status").text("Game complete!");
  $("#status").css("background-color", "rgb(136, 203, 153)");


  let endGame = `
  <div id="end-game">
    <form id="end-game-form" action=${queryParams.get('turkSubmitTo') + '/mturk/externalSubmit'} method="POST" >
      <input id="assignmentId" name="assignmentId" type="hidden" value=${queryParams.get('assignmentId')}>
      <input id="proposal" name="proposal" type="hidden" value=${proposal}>
      <button id="complete-hit" type="button" class="btn btn-primary">Complete HIT</button>
    </form>
  </div>`;
  if (queryParams.get('turkSubmitTo')) {
    $("#log").append(endGame);
  }
  $("#complete-hit").click(submitEndForm);

});

socket.on("end", function() {
  addEventToLog("Finished final game, wrapping up in a few seconds...");
  setTimeout(showEndGame, 3000);
});

socket.on("disconnected", function() {
  addEventToLog("The other player disconnected :( Please refresh to get connected to a new game.");
  $("#instruction-overlay").html("<div>The other player disconnected :( Please refresh to get connected to a new game.</div>");
});

socket.on("your_turn", function() {
  startTurn();
  audio.play();
});

socket.on("action", function(message) {
  let ac_data = message;
  ac_data = ac_data["data"];
  if (ac_data["data"] == "Proposal accepted" || ac_data["data"] == "Proposal rejected") {
    addEventToLog(ac_data["data"]);
  }
  let type = ac_data["type"];
  if (type === "utterance") {
    addEventToLog(ac_data["data"], ac_data["from_player"]);
  }
});

socket.on("proposal_available", function(proposal) {
  // Make this player respond to the proposal
  if (role !== "human") {
    console.error("Agent should not be receiving proposals...");
  }
  let timeline = $("#human #timeline");
  populateTimeline(timeline, proposal["proposal_data"], false, proposal["evt_scores"]);
  updateProposalInfo(proposal);
  addEventToLog("Agent made a proposal.");
  if (proposal["is_full_proposal"]) {
      setupProposalResponse();
  }
});

// -----------------------

function disableInputs() {
  console.log("disabling inputs");
  $(".actions-utterance input").val("");
  $(".actions-utterance input").prop("placeholder", "Waiting for the other player to respond...");
  $(".actions input").prop("disabled", true);
  $(".actions button").prop("disabled", true);
  $(".instructions").prop("hidden", true);
  $("#send-proposal").prop("hidden", true);
}

function enableInputs() {
  console.log("enabling inputs");
  $(".actions-utterance input").prop("placeholder", "Say something to the assistant...");
  $(".actions input").prop("disabled", false);
  $(".actions button").prop("disabled", false);
  $(".instructions").prop("hidden", false);
  $("#send-proposal").prop("hidden", false);
  $("#send-proposal > button").prop("disabled", false);
}

function setupProposalResponse() {
  $("#actions-proposal-response").prop("hidden", false);
  $("#actions-utterance").prop("hidden", true);
  $("#actions-proposal").prop("hidden", true);
}
function tearDownProposalResponse() {
  $("#actions-proposal-response").prop("hidden", true);
  $("#actions-utterance").prop("hidden", false);
  $("#actions-proposal").prop("hidden", false);
}

function submitAcceptProposal() {
  socket.emit("proposal_response", { "accept": true, "from_player": player_id });
  tearDownProposalResponse();
}
function submitRejectProposal(){
  $('.proposed').removeClass('proposed');
  socket.emit("proposal_response", { "accept": false, "from_player": player_id });
  tearDownProposalResponse();
}

function submitUtterance() {
  let utt = $("#utterance").val();
  if (utt.trim() === "") {
    return;
  }
  socket.emit("action", { "data": utt, "from_player": player_id, "type": "utterance" });
  var input = document.getElementById("utterance");
  input.value = "";
}

function setupHuman(data) {
  $("#human").show();
  $("#agent").hide();
  $("#human-doc").append("\n - " + data["preferences"].join("\n - "));
  let timeline = createTimeline(data["num_slots"]);
  $("#human #timeline").append(timeline);
  populateTimeline($("#human #timeline"), data, false);
  console.log(data);
  addEventToLog(`Randomly planning a travel itinerary gets a score of ${data["best_random_score"]}. Let's find something much better than that with your new travel agent!`);

  var modal = document.getElementById("human-modal");

  // Get the <span> element that closes the modal
  var span = document.getElementsByClassName("close")[0];

  // When the user clicks on <span> (x), close the modal
  span.onclick = function() {
    modal.style.display = "none";
  }

  // When the user clicks anywhere outside of the modal, close it
  window.onclick = function(event) {
    if (event.target == modal) {
      modal.style.display = "none";
    }
  }
}

function setupAgent(data) {
  $("#agent").show();
  $("#human").hide();
  events = data["events"];
  let timeline = createTimeline(data["num_slots"]);
  proposal = Array(timeline.length);
  $("#agent #timeline").append(timeline);
  populateTimeline($("#agent #timeline"), data, true);

  let geojson = {
    "type": "FeatureCollection",
    "features": data["events"].map(evt => wrapCoords(
        evt.loc,
        {
          "event": evt,
          "description": evt.name,
          "icon": evt.etype,
        })
    )
  }
  map.setData(geojson);
  map.registerOnClickCallback(e => (
    updateDetailView(JSON.parse(e.features[0]["properties"]["event"]))
  ));
  updateDetailView(data["events"][0]);

  // Get all binary features from events:
  feature_list = [];
  let feature_counts = {};
  let max_price = 0;
  for (let i = 0; i < events.length; i++) {
    let features = events[i]["features"];
    max_price = Math.max(max_price, events[i]["est_price"]);
    for (let key in features) {
      if (typeof features[key] == "boolean") {
        // Add to list of features:
        if (!feature_list.includes(key)) {
          feature_list.push(key);
          feature_counts[key] = 0;
        }
        // Add to feature counts:
        if (features[key]) {
          feature_counts[key] += 1;
        }
      }
    }
  }

  console.log("MAX PRICE: " + max_price);
  let slider = `<div class="slidecontainer">Max price: $<output id="slider-value"></output><br/><input type="range" min="0" max="${max_price}" value="${max_price}" class="slider" id="price-slider"></div>`
  $("#filter").append(slider);

  // Add checkboxes:
  let checkboxes = "";
  for (let i = 0; i < feature_list.length; i++) {
    checkboxes += `<br><input type="checkbox" class="filter-checkbox" id="${feature_list[i]}" name="${feature_list[i]}"> ${feature_list[i]}&nbsp;(${feature_counts[feature_list[i]]})`;
  }
  $("#filter").append(checkboxes);
  $(":checkbox").change(function() {
    filterMap();
  });
  const value = document.querySelector("#slider-value")
  const input = document.querySelector("#price-slider")
  value.textContent = input.value
  input.addEventListener("input", (event) => {
    value.textContent = Math.floor(event.target.value)
    filterMap();
  })

  var modal = document.getElementById("agent-modal");

  // Get the <span> element that closes the modal
  var span = document.getElementsByClassName("agent-close")[0];

  // When the user clicks on <span> (x), close the modal
  span.onclick = function() {
    modal.style.display = "none";
  }

  // When the user clicks anywhere outside of the modal, close it
  window.onclick = function(event) {
    if (event.target == modal) {
      modal.style.display = "none";
    }
  }
}

function updateDetailView(evt) {
  let evtElem = `
  <h4>${evt.name}</h4>
  Type: ${evt.etype}<br>
  Estimated price: $${evt.est_price}<br><br>
  `;
  for (let feat in evt.features) {
    evtElem += `<div>${feat}: ${evt.features[feat]}</div>`;
  }
  $("#detail-view").html(evtElem);
}

function createTimeline(numEvents) {
  let timeline = [];
  for (let i = 0; i < numEvents; i++) {
    let event = $("<div>", {
      "class": `timeline-slot event`,
      "id": `event-${2*i}`,
    });
    timeline.push(event);
    let travel = $("<div>", {
      "class": `timeline-slot travel`,
      "id": `travel-${2*i+1}`,
    });
    timeline.push(travel);
  }
  // Remove last travel slot
  timeline.pop();
  return timeline;
}

function populateTimeline(timeline, data, editable, evtScores) {
  /*
   * data: [
   *  {id_, type: {"event" | "travel"}, name, (features, etype,...)} | null
   *  ]
   */
  let slots = timeline.children();
  slots.each(function (i) {
    let slot = $(this);
    if (editable) {
      if (slot.hasClass("travel")) {
        slot.html(createSlotElement(data[i]));
        return;
      }
      // Attach autocompletes to each event slot
      slot.append($("<input>"));
      let ac = new autoComplete({
        placeHolder: "Type to search...",
        data: {src: data["events"], keys: ["name"]},
        selector: `#event-${i} input`,
        events: {
          input: {
            selection: (event) => {
              const timelineEventObj = event.detail.selection.value;
              ac.input.value = timelineEventObj.name;
              let idx = parseInt(i);
              updateProposal(idx, timelineEventObj, slot);
            },
            input: (event) => {
              ac.start();
              // Detect when input is cleared
              if (!ac.input.value) {
                let idx = parseInt(i);
                updateProposal(idx, null, slot);
              }
            }
          }
        }
      });
    } else {
      let evtScore = evtScores ? evtScores[i] : null;
      slot.html(createSlotElement(data[i], evtScore));
    }
  });
}

function createScoreEl(score) {
  return `<span class='evt-score evt-score-${score > 0 ? 'pos' : (score < 0 ? 'neg' : 'zero')}'>${score}</span>`;
}

function updateProposalInfo({
  proposal_data,
  total_score,
  evt_scores,
  itinerary_scores,
  price
}) {
  let itineraryDesc = itinerary_scores
    .map(({ desc, score }) => `${createScoreEl(score)} ${desc}`)
    .join("<br>")
  let travelScore = evt_scores[1] + evt_scores[3];
  let evtScore = evt_scores[0] + evt_scores[2] + evt_scores[4];
  $("#scorecard-content").html(`
  <div>Price: $${price}</div>
  Checking which wishlist items are satisfied by this itinerary:<br>
  <div>${itineraryDesc}</div>
  <hr/>
  <div>${createScoreEl(travelScore)} Total travel distance score</div>
  <div>${createScoreEl(evtScore)} Total event score</div>
  <div id="scorecard-score">Overall score: ${total_score}</div>
  `);
}

function createSlotElement(slotObj, evtScore) {
  if (!slotObj) {
    return `<p> --- </p>`;
  }
  if (slotObj.type === "event") {
    let feats = "";
    for (const [feat, val] of Object.entries(slotObj.features)) {
      feats += `${feat}: ${val}<br>`;
    }
    return `
    ${createScoreEl(evtScore)}<p class='evt-title'>${slotObj.name}</p><br>
    <p>Estimated price: $${slotObj.est_price}</p>
    <p>${feats}</p>`;
  } else if (slotObj.type === "travel") {
    let scoreEl = evtScore ? `<span class='evt-score evt-score-${evtScore > 0 ? 'pos' : 'neg'}'>${evtScore}</span>` : `<span></span>`;
    return `${scoreEl}<p>${slotObj.name}: ${slotObj.data} miles</p>`;
  } else {
    console.error("Unknown slot type ", slotObj);
  }
}

function route(evt1, evt2, slot, dir, idx) {
  // Calculate distance between events.
  let start = evt1.loc
  let end = evt2.loc

  let dist = Math.sqrt(
    Math.pow(start[0] - end[0], 2) + Math.pow(start[1] - end[1], 2)
  );
  dist *= 69;
  dist = (Math.round(dist * 10) / 10).toString();

  let output;
  let route;
  if (DEBUG) {
    // Add as straight line between events:
    route = [start, end];
    output = {"type": "travel", "name": "Estimated Travel", "data": dist};
  } else {
    const directions = getCyclingRoute(start, end);
    route = directions["route"];
    output = {"type": "travel", "name": "Cycling", "data": directions["duration"]};
  }
  map.drawRoute(route, idx);
  // Update timeline
  if (dir === "prev") {
    slot.prev().html(createSlotElement(output));
  } else if (dir === "next") {
    slot.next().html(createSlotElement(output));
  }
  return output;
}

function sendProposal() {
  let data = JSON.stringify(proposal);
  socket.emit("proposal", { "data": data, "from_player": player_id, "type": "proposal" });
  addEventToLog("You made a proposal.");
}

function startTurn() {
  $(".actions").prop("hidden", false);
  $("#status").text("Your turn!");
  $("#status").css("background-color", "#ff6969");
  $(".waiting").prop("hidden", true);
  enableInputs();
}

function endTurn() {
  disableInputs();
  $(".actions").prop("hidden", true);
  setStatusWaiting();
}

function setStatusWaiting(){
  $("#status").text("Waiting for other player to respond...");
  $("#status").css("background-color", "#fff7a3");
  $(".waiting").prop("hidden", false);
}

function addEventToLog(msg, from) {
  let message = msg.replace(/(?:\r\n|\r|\n)/g, '<br>');
  // If message has multiple lines, align left:
  let leftalign = "";
  if (message.indexOf("<br>") > -1 || message.indexOf("<br/>") > -1) {
    leftalign = "leftalign";
  }
  let actionLogEntry;
  if (!from && typeof from !== "number") {
    // var player_label = ``;
    actionLogEntry = `<div class="action-log-entry">${message}</div>`;
  } else if (from == player_id) {
    // var player_label = `<span style="color: #868687">[You]: </span>`;
    actionLogEntry = `<div class="action-log-entry playerMessage ${leftalign}">${message}</div>`;
  } else {
    // var player_label = `<span style="color: #007bff">[Partner]: </span>`;
    actionLogEntry = `<div class="action-log-entry partnerMessage">${message}</div>`;
  }
  // let actionLogEntry = `<div class="action-log-entry">${player_label}${message}</div>`;
  // let actionLogEntry = `<div class="action-log-entry playerMessage">${message}</div>`;
  $(".action-log").append(actionLogEntry);
  $(".action-log")[0].scrollTop = $(".action-log")[0].scrollHeight;
}

export function submitEndForm() {
  // Manually submit form to mturk, send event to our socket first
  let form = $("#end-game-form").serializeArray();
  // socket.emit("end_form", form);
  $("#end-game-form").submit();
}

/* -------------------------------------------------------------------------- */
/*                              Utils                                         */
/* -------------------------------------------------------------------------- */


function startTimer(duration, display, callback) {
  var timer = duration, minutes, seconds;
  setInterval(function () {
    minutes = parseInt(timer / 60, 10)
    seconds = parseInt(timer % 60, 10);

    minutes = minutes < 10 ? "0" + minutes : minutes;
    seconds = seconds < 10 ? "0" + seconds : seconds;

    display.text(minutes + ":" + seconds);

    if (--timer < 0) {
      callback()
    }
  }, 1000);
}

/* -------------------------------------------------------------------------- */
/*                              Event handlers                                */
/* -------------------------------------------------------------------------- */


$("document").ready(function () {
  $("button#submit-utterance").click(submitUtterance);
  let sendMessage = document.getElementById("utterance");
  sendMessage.addEventListener("keypress", function(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submitUtterance();
      // Mute audio:
      audio.pause();
    }
  });

  $("#send-proposal > button").click(sendProposal);
  $("button#accept-proposal").click(submitAcceptProposal);
  $("button#reject-proposal").click(submitRejectProposal);

  $("#start-game").on("click", (function() {
    alert("Testing");
    audio.pause();
  }));
});

// Proposal updating
function updateProposal(idx, event, proposalSlotElem) {
  proposal[idx] = event;
  // Add an event.
  if (event) {
    // Update distances to adjacent events
    if (idx - 2 >= 0 && proposal[idx - 2]) {
      proposal[idx - 1] = route(proposal[idx - 2], proposal[idx], proposalSlotElem, "prev", idx-1);
    }
    if (idx + 2 < proposal.length && proposal[idx + 2]) {
      proposal[idx + 1] = route(proposal[idx], proposal[idx + 2], proposalSlotElem, "next", idx+1);
    }
  // Remove an event.
  } else {
    if (idx > 1 && proposal[idx - 1]) {
      proposal[idx - 1] = null;
      map.removeLayer(`route-${idx-1}`);
      map.removeSource(`route-${idx-1}`);
      proposalSlotElem.prev().text(" --- ");
    }
    if (idx < proposal.length - 1 && proposal[idx + 1]) {
      proposal[idx + 1] = null;
      map.removeLayer(`route-${idx+1}`);
      map.removeSource(`route-${idx+1}`);
      proposalSlotElem.next().text(" --- ");
    }
  }
  // If proposal is empty, disable sending
  if (proposal.every(el => !el)) {
    $("#send-proposal > button").prop("disabled", true);
    $("#send-proposal-message").text("Fill in at least one event to send a proposal.");
    $("#send-proposal-message").show();
  // Check whether proposal events are unique.
  } else {
    let events = proposal.filter(x => x && x["type"] === "event");
    let allUnique = new Set(events).size === events.length;
    if (allUnique) {
      $("#send-proposal > button").prop("disabled", false);
      $("#send-proposal-message").hide();
    } else {
      $("#send-proposal > button").prop("disabled", true);
      $("#send-proposal-message").text("You cannot suggest the same destination twice.");
      $("#send-proposal-message").show();
    }
  }
  map.showProposal(proposal);
}

// Map
$("#event-type").on("change", function() {
  filterMap();
});

function filterMap() {
  let geojson;
  let filtered_events = [];
  let type = document.getElementById("event-type").value;
  // Iterate over food events:
  for (let i = 0; i < events.length; i++) {
    let checks = [
      (type == "all" || events[i].etype == type),
    ]
    // Iterate over checkboxes:
    for (let j = 0; j < feature_list.length; j++) {
      let checkbox = document.getElementById(feature_list[j]);
      if (checkbox.checked) {
        checks.push(events[i]["features"][feature_list[j]]);
      } else {
        checks.push(true);
      }
    }
    // Check price:
    checks.push(events[i]["est_price"] <= document.querySelector("#price-slider").value);
    if (checks.every(Boolean)) {
      filtered_events.push(events[i]);
    }
    geojson = {
      "type": "FeatureCollection",
      "features": filtered_events.map(evt => wrapCoords(
          evt.loc,
          {
            "event": evt,
            "description": evt.name,
            "icon": evt.etype,
          })
      )
    }
  }
  map.setData(geojson);
  updateDetailView(filtered_events[0]);
}
