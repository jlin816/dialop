let mturkQueryString = window.location.href.slice(window.location.href.indexOf("?"));
let queryParams = new URLSearchParams(mturkQueryString);
let socket = io({ query: Object.fromEntries(queryParams.entries()) });
let player_id;
let scale;
let proposal;
let gameOver = false;
let audio;
let qualification_mode = false;
let role;
let endGame;
let calendars = [];
let num_flights_selected = 0;

const NUM_PRACTICE_ROUNDS = 1;
const NUM_ROUNDS = 1;
const DEBUG = true;
const COLORS = ["#cd5800", "#9f65b5", "#52a666", "#a65252"];

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
  if (data["role"] == "agent") {
    addEventToLog(`Your group achieved a score of ${parseInt(data["reward"])}.`);
  }
  else {
    let player_score = parseInt(data["player_reward"]);
    let group_score = parseInt(data["reward"]);
    let partner_score = group_score - player_score;
    addEventToLog(`Your group achieved a score of ${group_score}. You got ${player_score} points and your partner got ${partner_score} points.`);
  }
  console.log("OBS: ", data["obs"]);
  if (!qualification_mode) {
    addEventToLog(`You earned a bonus of $${data["bonus"].toFixed(2)}.`);
    addEventToLog(`Please refresh the page to start a new game.`);
  } else {
    addEventToLog(`Thanks for playing our game! Please refresh to start a new game.`);
  }
  $("#send-proposal").prop("disabled", true);
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
  addEventToLog("One of the other players disconnected :( Please refresh to get connected to a new game.");
  $("#instruction-overlay").html("<div>The other player disconnected :( Please refresh to get connected to a new game.</div>");
});

socket.on("your_turn", function(data) {
  startTurn(data["vroom"]);
  audio.play();
});

socket.on("end_turn", function(data) {
});

socket.on("action", function(message) {
  let ac_data = message["data"];
  addEventToLog(ac_data["data"], ac_data["from_player"], ac_data["virtual_room_id"]);
});

socket.on("proposal_available", function(proposal) {
  if (role !== "human") {
    console.error("Agent should not be receiving proposals...");
  }
  showFlightInCalendar(proposal["proposal_data"], calendars[0]);
  $(".flight").removeClass("selected");
  $(".flight").each(function() {
    if (JSON.stringify($(this).data()) === JSON.stringify(proposal["proposal_data"])) {
      $(this).addClass("selected");
    }
  });
  updateProposalInfo(proposal);
  addEventToLog("Agent made a proposal.");
  setupProposalResponse();
});

// -----------------------

function disableInputs() {
  console.log("disabling inputs");
  $(".actions-utterance input").val("");
  $(".actions-utterance input").prop("placeholder", "Waiting for the other player to respond...");
  $(".actions input").prop("disabled", true);
  $(".actions button").prop("disabled", true);
  $("#proposal-sent-message").hide();
}

function enableInputs(vroom) {
  let selector = (role !== "agent" || vroom === undefined) ? "" : `#chat-${vroom}`;
  $(`.actions-utterance input`)
    .prop("placeholder", "Say something to the assistant...");
  $(`.actions input`).prop("disabled", false);
  $(`.actions button`).prop("disabled", false);
  $("#send-proposal > button").prop("disabled", false);
}

function setupProposalResponse() {
  $("#actions-proposal-response").prop("hidden", false);
  $(".actions-utterance").prop("hidden", true);
  $("#actions-proposal").prop("hidden", true);
}
function tearDownProposalResponse() {
  $("#actions-proposal-response").prop("hidden", true);
  $(".actions-utterance").prop("hidden", false);
  $("#actions-proposal").prop("hidden", false);
}

function submitAcceptProposal() {
  socket.emit("proposal_response", {
    "accept": true,
    "from_player": player_id,
    "virtual_room_id": player_id
  });
  tearDownProposalResponse();
}
function submitRejectProposal(){
  $('.proposed').removeClass('proposed');
  socket.emit("proposal_response", {
    "accept": false,
    "from_player": player_id,
    "virtual_room_id": player_id
  });
  tearDownProposalResponse();
}

function submitUtterance(evt) {
  let utt;
  let virtualRoomId = evt.data.virtualRoomId;
  if (role === "agent") {
    utt = $(`#chat-${virtualRoomId} .utterance`).val();
    $(`#chat-${virtualRoomId} .utterance`).val("");
  } else {
    utt = $(".utterance").val();
    $(".utterance").val("");
  }
  if (utt.trim() === "") {
    return;
  }
  socket.emit("action", {
    "data": utt,
    "from_player": player_id,
    "virtual_room_id": evt.data.virtualRoomId,
    "type": "utterance"
  });
}

function showFlightInCalendar(flight, cal) {
  console.log(flight);
  let existingFlight = cal.getEventById("flight");
  if (existingFlight) {
    existingFlight.remove();
    console.log("removed existing");
    console.log(existingFlight);
  } else {
    console.log("null exisiting");
  }
  cal.addEvent({
    id: "flight",
    title: `${flight.carrier} Flight`,
    start: flight.start,
    end: flight.end,
    backgroundColor: "white",
    borderColor: "red",
    textColor: "red",
  });
  let duration = flight.start.split("T")[1];
  cal.scrollToTime(duration);
}

function createCalendarElem(events, container, color) {
  let calendarEl = container.get()[0];
  let calendar = new FullCalendar.Calendar(calendarEl, {
    initialView: "timeGridThreeDay",
    views: {
      timeGridThreeDay: {
        type: "timeGrid",
        duration: { days: 3 },
        allDaySlot: false,
      }
    },
    headerToolbar: {
      start: "title",
      center: "",
      end: "",
    },
    aspectRatio: 5,
    handleWindowResize: true,
    scrollTime: "09:00:00",
    initialDate: "2023-05-31",
    events: events,
    eventColor: color,
    slotEventOverlap: false
  });
  calendar.render();
  calendars.push(calendar);
}

function prettyPrintDuration(fl) {
  let date = new Date(fl.start);
  let startTime = new Date(fl.start).toLocaleString(
    "en-US", {hour: "numeric", hour12: true, minute: "numeric"});
  let endTime = new Date(fl.end).toLocaleString(
    "en-US", {hour: "numeric", hour12: true, minute: "numeric"});
  return `${date.getMonth() + 1}/${date.getDate()} ${startTime} — ${endTime}`
}

function createSingleFlightElem(fl, cal, idx) {
  return $("<li/>", {class: "flight list-group-item"}).data(fl).html(
    `<div class="flight-logo"><img src="media/${fl.carrier.toLowerCase()}.png"/></div>
      <div>
        <div class="flight-times">${prettyPrintDuration(fl)}</div>
        <div class="flight-carrier">${fl.carrier}</div>
      </div>
      <div class="flight-price">$${fl.price}</div>
  `).click(function() {
    showFlightInCalendar(fl, cal);
    if (role === "agent" && idx !== undefined) {
      if (!$(`#player-row-${idx} .flight`).hasClass("selected")) {
        num_flights_selected += 1;
      }
      if (num_flights_selected === 2) {
        $("#send-proposal").prop("disabled", false);
      }
    }
    if (role === "agent" && idx !== undefined) {
      $(`#player-row-${idx} .flight`).removeClass("selected");
      $(this).addClass("selected");
      updateProposal(idx, fl);
    }
  });
}

function updateProposal(idx, fl) {
  proposal[parseInt(idx)] = fl;
  $(`#agent #proposal-${idx}`).html(
    `<b>User ${idx} Booking</b><br>${fl.carrier}<br>${prettyPrintDuration(fl)}`
  );
}

function createFlightsElem(flights, container, cal, idx) {
  container.append(
    $("<div/>", {id: `flights-${idx}`, class: "flights card"})
    .append($("<ul/>", {class: "list-group list-group-flush"}))
  );
  flights.forEach(f => $(`#flights-${idx} ul`).append(createSingleFlightElem(f, cal, idx)));
}

function createScoreEl(score) {
  return `<span class='evt-score evt-score-${score >= 0 ? 'pos' : 'neg'}'>${score}</span>`;
}

function updateProposalInfo({
  proposal_data,
  proposal_readable,
  cost
}) {
  $("#scorecard-content").html(`
  <div>${proposal_readable}</div>
  <hr/>
  <div>${createScoreEl(cost.calendar)} Try not to skip important meetings</div>
  <div>${createScoreEl(cost.price)} Get a good deal on the flight price</div>
  <div>${createScoreEl(cost.arrival_time)} Have everyone arrive around the same time</div>
  <div id="scorecard-score">Overall score: ${cost.total}</div>
  `);
  $("#scorecard").height("calc(50% - 20px)");
  $("#flights-container").height("50%");
}

function addProposalResponseElem() {
  let elem =
  `<div id="actions-proposal-response" class="row" hidden>
    <div class="col">
      <button id="accept-proposal" class="btn btn-success btn-block">Accept</button>
    </div>
    <div class="col">
      <button id="reject-proposal" class="btn btn-danger btn-block">Reject</button>
    </div>
  </div>`;
  $(".actions").append(elem);
  $("button#accept-proposal").click(submitAcceptProposal);
  $("button#reject-proposal").click(submitRejectProposal);
}

function createNWayChat(n) {
  // Create tab navigation
  let nav = $("<ul>", {
    class: "nav nav-tabs",
    id: "chat-tab-nav",
    role: "tablist"
  })
  for (let i = 0; i < n; i++) {
    nav.append(
      $("<li>", {
        class: `nav-item`,
        role: "presentation"
      }).append(
        $("<button>", {
          type: "button",
          class: `nav-link ${i === 0 ? 'active' : ''}`,
          id: `chat-${i}-tab`,
          "data-player-id": i,
          // JS handled by bootstrap
          "data-toggle": "tab",
          "data-target": `#chat-${i}`,
        }).text(`User ${i}`)
          .append($("<span>", {
            class: "badge badge-danger nav-indicator",
            id: `nav-indicator-${i}`,
            hidden: true,
          }).text("1"))
          .click(() => $(`#nav-indicator-${i}`).prop("hidden", true))
      )
    );
  }

  // Create N chats
  let chatHtml = $(".chat").html();
  console.log(chatHtml);
  let content = $("<div>", {
    class: "tab-content",
    id: "chat-content",
  });
  for (let i = 0; i < n; i++) {
    content.append(
      $("<div>", {
        class: `tab-pane ${i === 0 ? 'active' : ''}`,
        id: `chat-${i}`,
        role: "tabpanel",
      }).append(chatHtml)
    );
  }
  $(".chat").parent().append(nav);
  $(".chat").parent().append(content);
  $(".chat").remove();

  // Attach event handlers
  for (let i = 0; i < n; i++) {
    $(`#chat-${i} button.submit-utterance`).click({virtualRoomId: i}, submitUtterance);
    $(`#chat-${i} .utterance`).keypress(function(event) {
      if (event.key === "Enter" && !event.shiftKey) {
        submitUtterance({data: {virtualRoomId: i}});
        // Mute audio:
        audio.pause();
        return false;
      }
    });
  }
}

function setupHuman(data) {
  addEventToLog("You and your friends are trying to book flights to travel together.");
  $("#human").show();
  $("#agent").hide();
  data.calendar.forEach(evt => {
    let start = new Date(evt.start);
    let end = new Date(evt.end);
    let duration = (end - start) / 1000 / 60;
    let imp_text = "";
    if (duration >= 120) {
      imp_text = "Importance";
    } else if (duration >= 60) {
      imp_text = "Imp.";
    }
    let importance;
    if (evt.importance <= 3) {
      importance = `Low ${imp_text} (${evt.importance})`;
    } else if (evt.importance <= 6) {
      importance = `Medium ${imp_text} (${evt.importance})`;
    } else {
      importance = `High ${imp_text} (${evt.importance})`;
    }
    evt.title = importance;
    // Check if evt in shared_calendar:
    let shared_evt = data.shared_calendar.find(e => e.start === evt.start && e.end === evt.end);
    if (shared_evt) {
      evt.backgroundColor = `rgb(${colorScale(evt.importance / 10, [110, 161, 212], [0, 78, 156])})`;
    } else {
      evt.backgroundColor = `rgb(${colorScale(evt.importance / 10, [255, 255, 255], [0, 0, 0])})`;
    }
  });

  createCalendarElem(data.calendar, $("#human #calendar-container"));
  createFlightsElem(data.flights, $("#human #flights-container"), calendars[0]);
  addProposalResponseElem();

  // Event handlers
  $("button.submit-utterance").click({virtualRoomId: player_id}, submitUtterance);
  $(".utterance").keypress(function(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      submitUtterance({data: {virtualRoomId: player_id}});
      // Mute audio:
      audio.pause();
      return false;
    }
  });

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
  addEventToLog("You are the travel assistant.");
  $("#agent").show();
  $("#human").hide();
  data.player_data.forEach((p, i) => {
    let playerRow = $("<div/>", {id: `player-row-${i}`, class: "player-row"})
      .append($("<div/>", {id: "calendar-container"}))
      .append($("<div/>", {id: "flights-container", class: "flights-container-agent"}));
    $("#agent").append(playerRow);
    createCalendarElem(p.shared_calendar, $(`#player-row-${i} #calendar-container`), COLORS[i]);
    createFlightsElem(p.flights, $(`#player-row-${i} #flights-container`),
      calendars[i], i);
    $("#agent #proposal-container").append(
      $("<div>", {
        class: "proposal-slot",
        id: `proposal-${i}`,
        style: `border: 2px solid ${COLORS[i]}`
      }).html(`<b>User ${i} Booking</b><br>NONE`));
  });
  proposal = Array(data.player_data.length);
  createNWayChat(data.player_data.length);

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

function sendProposal() {
  let data = JSON.stringify(proposal);
  socket.emit("proposal", { "data": data, "from_player": player_id, "type": "proposal" });
  addEventToLog("You made a proposal.");
}

function startTurn(vroom) {
  $("#status").text("Your turn!");
  $("#status").css("background-color", "#ff6969");
  // If vroom, enable actions only in a particular room (for agent)
  let selector = (role !== "agent" || vroom === undefined) ? "" : `#chat-${vroom}`;
  $(`.actions`).prop("hidden", false);
  $(`.waiting`).prop("hidden", true);
  if (role === "agent" && vroom !== undefined) {
    $(`#nav-indicator-${vroom}`).prop("hidden", false);
  }
  enableInputs(vroom);
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

function addEventToLog(msg, from, virtualRoom) {
  let message = msg.replace(/(?:\r\n|\r|\n)/g, '<br>');
  // If message has multiple lines, align left:
  let leftalign = "";
  if (message.indexOf("<br>") > -1 || message.indexOf("<br/>") > -1) {
    leftalign = "leftalign";
  }
  let actionLogEntry;
  if (!from && typeof from !== "number") {
    actionLogEntry = `<div class="action-log-entry">${message}</div>`;
  } else if (from == player_id) {
    actionLogEntry = `<div class="action-log-entry playerMessage ${leftalign}">${message}</div>`;
  } else {
    actionLogEntry = `<div class="action-log-entry partnerMessage">${message}</div>`;
  }
  // Note this will append to all virtual room logs if virtualRoom is not
  // specified.
  let selector = (role === "agent" && virtualRoom !== undefined) ?
    (`#chat-${virtualRoom} .action-log`) : ".action-log";
  $(selector).append(actionLogEntry);
  $(selector)[0].scrollTop = $(selector)[0].scrollHeight;
}

function submitEndForm() {
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

function colorScale(frac, startColor, endColor) {
  let [r1, g1, b1] = startColor;
  let [r2, g2, b2] = endColor;
  return [frac * (r2 - r1) + r1,
          frac * (g2 - g1) + g1,
          frac * (b2 - b1) + b1];
}

/* -------------------------------------------------------------------------- */
/*                              Event handlers                                */
/* -------------------------------------------------------------------------- */

$("document").ready(function () {
  $("#send-proposal").click(sendProposal);
});
