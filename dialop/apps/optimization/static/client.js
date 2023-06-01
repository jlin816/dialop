let mturkQueryString = window.location.href.slice(window.location.href.indexOf("?"));
let queryParams = new URLSearchParams(mturkQueryString);
let socket = io({ query: Object.fromEntries(queryParams.entries()) });
let player_id;
let originalTable;
let showBestSolution = false;
let playerTable;
let combinedTable;
let scale;
let proposal;
let bestProposal;
let gameOver = false;
let audio;
let qualification_mode = false;

const NUM_PRACTICE_ROUNDS = 1;
const NUM_ROUNDS = 1;

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
  console.log("BEGIN");
  console.log(data["worker_id"]);
  $("#instruction-overlay").prop("hidden", true);
  audio.play();

  // Prep the game
  $("#status").text("Starting game. Please reference the instructions if needed.");
  $(".actions").prop("hidden", true);
  player_id = data["player_id"];

  setupTable(data["table"], data["scale"]);
  setupProposalForm(data["table"]);

  addEventToLog("Starting new game...");
  if (qualification_mode) {
    addEventToLog("The average player received a score of " + parseInt(data["max_reward"] * data["scale"] / 1.1) + ". See if you can beat that!");
    addEventToLog("Remember that your partner sees numbers on a different scale, so please don't try to communicate the numbers directly and instead focus on relative values.");
  }

  setTimeout(function () {
    enableInputs();
  }, 1000);
});

socket.on("end_game", function(data) {
  disableInputs();
  gameOver = true;
  for (let i = 0; i < originalTable.length; i++) {
    for (let j = 0; j < originalTable[i].length; j++) {
      removeOpacity(i, j);
    }
  }
  addEventToLog(`Your proposal had value ${parseInt(data["your_reward"] * data["scale"])}. The best proposal had value ${parseInt(data["best_reward"] * data["scale"])}.`);
  if (!qualification_mode) {
    addEventToLog(`You earned a bonus of $${data["bonus"].toFixed(2)}.`);
    addEventToLog(`Please refresh the page to start a new game.`);
  } else {
    addEventToLog(`Thank you for playing our game! Please refresh to start a new game.`);
  }


  $(".waiting").prop("hidden", true);
  $(".scratchpad").css("padding-top", "20px");
  $("#status").text("Game complete!");
  $("#status").css("background-color", "rgb(136, 203, 153)");
  $("#toggle-best").css("display", "inline-block");

  let cells = data["proposal"];
  $('.proposed').removeClass('proposed');
  $('.outlined').removeClass('outlined');
  for (let i = 0; i < cells.length; i++) {
    let cell = cells[i];
    console.log(cell);
    $(`#${cell}`).addClass("outlined");
  }
  playerTable = data["player_table"];
  combinedTable = data["combined_table"];
  proposal = data["proposal"];
  bestProposal = data["best_proposal"];
  scale = data["scale"];

  endGame = `
  <div id="end-game">
    <form id="end-game-form" action=${queryParams.get('turkSubmitTo') + '/mturk/externalSubmit'} method="POST" >
      <input id="assignmentId" name="assignmentId" type="hidden" value=${queryParams.get('assignmentId')}>
      <input id="proposal" name="proposal" type="hidden" value=${proposal}>
      <input id="bestProposal" name="bestProposal" type="hidden" value=${bestProposal}>
      <button type="button" class="btn btn-primary" onClick="submitEndForm()">Complete HIT</button>
    </form>
  </div>`;
  if (queryParams.get('turkSubmitTo')) {
    $("#log").append(endGame);
  }

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
  ac_data = message;
  ac_data = ac_data["data"];
  addEventToLog(ac_data["data"], from=ac_data["from_player"]);
});

socket.on("proposal_available", function(data) {
  // Make this player respond to the proposal
  // Iterate over cells and highlight them:
  console.log(data);
  let cells = data["proposal_data"]["cells"];
  console.log(cells);
  for (let i = 0; i < cells.length; i++) {
    let cell = cells[i];
    $(`#${cell}`).addClass("proposed");
  }
  setupProposalResponse();
});

socket.on("max_games", function() {
  // Hide instruction overlay:
  $("#instruction-overlay").html("<div>Thank you for your participation! You have reached the maximum number of games.</div>");
  endGame = `
  <div id="end-game">
    <p>Click the following button to submit your HIT for approval:</p>
    <form id="end-game-form" style="text-align: center;" action=${queryParams.get('turkSubmitTo') + '/mturk/externalSubmit'} method="POST" >
      <input id="assignmentId" name="assignmentId" type="hidden" value=${queryParams.get('assignmentId')}>
      <input id="empty-val" name="empty-val" type="hidden" value="None"}>
      <button type="button" class="btn btn-primary" onClick="submitEndForm()">Complete HIT</button>
    </form>
  </div>`;
  if (queryParams.get('turkSubmitTo')) {
    $("#instruction-overlay").append(endGame);
  }
});


// -----------------------

function disableInputs() {
  $(".actions-utterance input").val("");
  $(".actions-utterance input").prop("placeholder", "Waiting for the other player to respond...");
  $(".actions input").prop("disabled", true);
  $(".actions button").prop("disabled", true);
  $(".instructions").prop("hidden", true);
}

function enableInputs() {
  $(".actions-utterance input").prop("placeholder", "Say something to the assistant...");
  $(".actions input").prop("disabled", false);
  $(".actions button").prop("disabled", false);
  $(".instructions").prop("hidden", false);
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
  socket.emit("action", { "data": utt, "from_player": player_id, "type": "utterance" });
  var input = document.getElementById("utterance");
  input.value = "";
}

function toggleSolution() {
  if (!showBestSolution) {
    showBestSolution = true;
    setupTable(combinedTable, scale);
    cells = proposal;
    for (let i = 0; i < cells.length; i++) {
      let cell = cells[i];
      $(`#${cell}`).addClass("outlined");
    }
    cells = bestProposal;
    for (let i = 0; i < cells.length; i++) {
      let cell = cells[i];
      $(`#${cell}`).addClass("proposed");
    }
  } else {
    showBestSolution = false;
    setupTable(playerTable, scale);
    cells = proposal;
    for (let i = 0; i < cells.length; i++) {
      let cell = cells[i];
      $(`#${cell}`).addClass("outlined");
    }
  }
}

const COLOR_SCALE= [
  // Note higher values are better
  // red
  { pct: 0.0, color: { r: 248, g: 105, b: 107 } },
  // gray
  { pct: 0.5, color: { r: 241, g: 241, b: 241 } },
  // green
  { pct: 1.0, color: { r: 99, g: 190, b: 123 } },
];
const MAX_TABLE_VALUE = 100;

function getColorForPercentage(pct) {
  for (var i = 1; i < COLOR_SCALE.length - 1; i++) {
      if (pct < COLOR_SCALE[i].pct) {
          break;
      }
  }
  var lower = COLOR_SCALE[i - 1];
  var upper = COLOR_SCALE[i];
  var range = upper.pct - lower.pct;
  var rangePct = (pct - lower.pct) / range;
  var pctLower = 1 - rangePct;
  var pctUpper = rangePct;
  var color = {
      r: Math.floor(lower.color.r * pctLower + upper.color.r * pctUpper),
      g: Math.floor(lower.color.g * pctLower + upper.color.g * pctUpper),
      b: Math.floor(lower.color.b * pctLower + upper.color.b * pctUpper)
  };
  return 'rgba(' + [color.r, color.g, color.b].join(',') + ', 1.0)';
  // or output as hex if preferred
}

var highlighted_cells = new Set();

function removeOpacity(row, col) {
  for (let i = 0; i < originalTable.length; i++) {
    if (i != row) {
      let other_cell = document.getElementById("cell-" + i + "-" + col);
      other_cell.style.filter = "none";
    }
  }
  for (let i = 0; i < originalTable[0].length; i++) {
    if (i != col) {
      let other_cell = document.getElementById("cell-" + row + "-" + i);
      other_cell.style.filter = "none";
    }
  }
}
function addOpacity(row, col) {
  for (let i = 0; i < originalTable.length; i++) {
    if (i != row) {
      let other_cell = document.getElementById("cell-" + i + "-" + col);
      other_cell.style.filter = "brightness(0.95)";
    }
  }
  for (let i = 0; i < originalTable[0].length; i++) {
    if (i != col) {
      let other_cell = document.getElementById("cell-" + row + "-" + i);
      other_cell.style.filter = "brightness(0.95)";
    }
  }
}

function setupTable(table, scale) {
  const container = document.getElementById("table");
  // For tracking what values we had originally
  originalTable = table.slice();

  function headerRenderer(instance, td, row, col, prop, value, cellProperties) {
    Handsontable.renderers.TextRenderer.apply(this, arguments);
    cellProperties.readOnly = true;
    td.className = "htCenter htMiddle";
    td.fontSize = "15px";
    td.id = "cell-" + row + "-" + col;
  }

  function cellRenderer(instance, td, row, col, prop, value, cellProperties) {
    Handsontable.renderers.NumericRenderer.apply(this, arguments);
    if (originalTable[row][col] === '') {
      cellProperties.readOnly = true;
      td.style.backgroundColor = '#EEE';
    } else {
      cellProperties.readOnly = true;
      td.style.backgroundColor = getColorForPercentage(value / (MAX_TABLE_VALUE * scale));
    }


    td.style.fontWeight = 'bold';
    td.style.fontSize = '20px';
    td.className = "htCenter htMiddle numberCell";
    td.id = "cell-" + row + "-" + col;
    td.onclick = function() {
      if (highlighted_cells.has(td.id)) {
        highlighted_cells.delete(td.id);
        td.classList.remove("outlined");
        removeOpacity(row, col);
      } else {
        highlighted_cells.add(td.id);
        td.classList.add("outlined");
        socket.emit("click", {"data": [row, col], "from_player": player_id});
        // Remove highlight from all cells in same row and column:
        for (let i = 0; i < table.length; i++) {
          if (i != row) {
            let other_cell = document.getElementById("cell-" + i + "-" + col);
            if (highlighted_cells.has(other_cell.id)) {
              highlighted_cells.delete(other_cell.id);
              other_cell.classList.remove("outlined");
              removeOpacity(i, col);
            }
          }
        }
        for (let i = 0; i < table[0].length; i++) {
          if (i != col) {
            let other_cell = document.getElementById("cell-" + row + "-" + i);
            if (highlighted_cells.has(other_cell.id)) {
              highlighted_cells.delete(other_cell.id);
              other_cell.classList.remove("outlined");
              removeOpacity(row, i);
            }
          }
        }
      }
      // Iterate over highlighted cells:
      if (!gameOver) {
        for (let cell of highlighted_cells) {
          let cell_id = document.getElementById(cell);
          addOpacity(cell_id.id.split("-")[1], cell_id.id.split("-")[2]);
        }
      }
    }
 }
 // Set height equal to width
  const hot = new Handsontable(container, {
    data: table,
    rowHeaders: false,
    colHeaders: false,
    height: 'auto',
    width: '100%',
    height: '100%',
    colWidths: 600 / originalTable.length / 6,
    rowHeights: 600 / originalTable.length,
    stretchH: 'all',
    manualColumnResize: true,
    licenseKey: 'non-commercial-and-evaluation',
  });

  // Make known cells uneditable
  hot.updateSettings({
    cells(row, col) {
      const cellProperties = {};
      if (row == 0 || col == 0) {
        cellProperties.renderer = headerRenderer;
      } else {
        cellProperties.renderer = cellRenderer;
      }
     return cellProperties;
    }
  });
}

function setupProposalForm(table) {
  // // Build form
  let form = $("<form id='proposal-form'>");
  form.append($("<button type='button' id='submit' class='btn btn-primary' onClick='submitProposal()'>").text("Send Proposal"));
  // Add form to the page
  $("#proposal-form-container").append(form);
}

function submitProposal() {
  let proposal = Array.from(highlighted_cells);
  // Check that proposal is valid:
  // 1. Has five elements:
  num_rows = originalTable.length - 1;
  if (proposal.length != num_rows) {
    alert("Proposal must have exactly " + num_rows + " elements! You must click on cells in the table to highlight them before sending a proposal.");
    return;
  }
  // 2. Each row and column is used only once:
  let rows = new Set();
  let cols = new Set();
  for (let i = 0; i < proposal.length; i++) {
    let cell = proposal[i];
    let row = parseInt(cell.split("-")[1]);
    let col = parseInt(cell.split("-")[2]);
    if (rows.has(row) || cols.has(col)) {
      alert("Invalid proposal!");
      return;
    }
    rows.add(row);
    cols.add(col);
  }
  // Compute proposal data:
  let proposalData = [];
  for (let i = 0; i < proposal.length; i++) {
    let cell = proposal[i];
    let row = parseInt(cell.split("-")[1]);
    let col = parseInt(cell.split("-")[2]);
    proposalData.push({
      "name": "paper-" + (col-1),
      "value": originalTable[row][0],
    });
  }
  let data = JSON.stringify({
    "assignments": proposalData,
    "cells": Array.from(highlighted_cells)
  });

  socket.emit("proposal", { "data": data, "from_player": player_id, "type": "proposal" });
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

function carrier_name(opt) {
  for (const [key, value] of Object.entries(opt)) {
    if (key.indexOf("carrier") > -1 && value == 1) {
      carrier = key.slice(key.indexOf("=") + 1);
      return carrier
    }
  }
}

function addEventToLog(message, from=-1) {
  message = message.replace(/(?:\r\n|\r|\n)/g, '<br>');
  // If message has multiple lines, align left:
  let leftalign = "";
  if (message.indexOf("<br>") > -1 || message.indexOf("<br/>") > -1) {
    leftalign = "leftalign";
  }
  let actionLogEntry;
  if (from == -1) {
    actionLogEntry = `<div class="action-log-entry">${message}</div>`;
  } else if (from == player_id) {
    actionLogEntry = `<div class="action-log-entry playerMessage ${leftalign}">${message}</div>`;
  } else {
    actionLogEntry = `<div class="action-log-entry partnerMessage">${message}</div>`;
  }
  $(".action-log").append(actionLogEntry);
  $(".action-log")[0].scrollTop = $(".action-log")[0].scrollHeight;
}

function submitEndForm() {
  // Manually submit form to mturk, send event to our socket first
  let form = $("#end-game-form").serializeArray();
  $("#end-game-form").submit();
}

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

var input = document.getElementById("utterance");
input.addEventListener("keypress", function(event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    submitUtterance();
    // Mute audio:
    audio.pause();
  }
});

$("#start-game").on("click", (function() {
  alert("Testing");
  audio.pause();
}));
