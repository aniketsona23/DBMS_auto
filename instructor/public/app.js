// app.js — parser + UI wiring
document.addEventListener("DOMContentLoaded", () => {
  // Database credential inputs
  const dbHost = document.getElementById("dbHost");
  const dbPort = document.getElementById("dbPort");
  const dbUser = document.getElementById("dbUser");
  const dbPass = document.getElementById("dbPass");
  const dbNameSample = document.getElementById("dbNameSample");
  const dbNameEval = document.getElementById("dbNameEval");
  const testConnectionBtn = document.getElementById("testConnectionBtn");
  const connectionStatus = document.getElementById("connectionStatus");

  const solutionSqlInput = document.getElementById("solutionSqlInput");
  const solutionSqlStatus = document.getElementById("solutionSqlStatus");
  const dbFileInputSample = document.getElementById("dbFileInputSample");
  const dbFileInputEval = document.getElementById("dbFileInputEval");
  const questionsPdfInput = document.getElementById("questionsPdfInput");
  const pdfStatus = document.getElementById("pdfStatus");
  const resetDbBtnSample = document.getElementById("resetDbBtnSample");
  const resetDbBtnEval = document.getElementById("resetDbBtnEval");
  const clearBtn = document.getElementById("clearBtn");
  const parseBtn = document.getElementById("parseBtn");
  const createBtn = document.getElementById("createBtn");
  const queriesDiv = document.getElementById("queries");
  const output = document.getElementById("output");
  const downloadPackageBtn = document.getElementById("downloadPackageBtn");
  const downloadListScoresBtn = document.getElementById(
    "downloadListScoresBtn"
  );
  const packageRow = document.getElementById("packageRow");
  const allowedStartTime = document.getElementById("allowedStartTime");

  // Store PDF file and solution SQL content
  let questionsPdfFile = null;
  let solutionSqlContent = "";

  // Helper function to analyze query type from SQL string
  function analyzeQueryType(query) {
    const q = query.trim().toUpperCase();
    if (q.match(/^\s*SELECT\b/)) return "select";
    if (q.match(/\bCREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\b/)) return "function";
    if (q.match(/\bCREATE\s+(?:OR\s+REPLACE\s+)?VIEW\b/)) return "view";
    if (q.match(/\b(?:CREATE|ALTER|DROP)\s+TABLE\b/)) return "ddl_dml";
    if (q.match(/\b(?:INSERT|UPDATE|DELETE)\b/)) return "dml";
    return "unknown";
  }

  // Helper to collect DB credentials
  function getCommonCreds() {
    const creds = {
      host: dbHost.value.trim() || "localhost",
      port: parseInt(dbPort.value) || 3306,
      user: dbUser.value.trim() || "",
      password: dbPass.value || "",
    };
    console.log("Collected credentials:", { ...creds, password: "***" });
    return creds;
  }

  // Test connection button
  if (testConnectionBtn) {
    testConnectionBtn.addEventListener("click", async () => {
      // Prefer testing sample DB if present; otherwise eval DB
      const common = getCommonCreds();
      const sampleCreds = {
        ...common,
        database: (dbNameSample?.value || "").trim(),
      };
      const evalCreds = {
        ...common,
        database: (dbNameEval?.value || "").trim(),
      };
      const creds = sampleCreds.database ? sampleCreds : evalCreds;
      if (!creds.user || !creds.database) {
        connectionStatus.textContent =
          "⚠ Please enter username and database name";
        connectionStatus.className = "status-warning";
        return;
      }

      connectionStatus.textContent = "Testing connection...";
      connectionStatus.className = "status-info";

      try {
        const res = await fetch("/test-connection", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(creds),
        });

        if (res.ok) {
          connectionStatus.textContent = "✓ Connection successful";
          connectionStatus.className = "status-success";
        } else {
          const text = await res.text();
          connectionStatus.textContent = "✗ Connection failed: " + text;
          connectionStatus.className = "status-error";
        }
      } catch (e) {
        connectionStatus.textContent = "✗ Connection test failed: " + e;
        connectionStatus.className = "status-error";
      }
    });
  }

  // solution.sql file input handler - parse file in frontend
  if (solutionSqlInput) {
    solutionSqlInput.addEventListener("change", async (e) => {
      const f = e.target.files[0];
      if (!f) {
        solutionSqlContent = "";
        solutionSqlStatus.textContent = "";
        return;
      }
      try {
        solutionSqlContent = await f.text();
        solutionSqlStatus.textContent = `✓ ${f.name} loaded (${(
          f.size / 1024
        ).toFixed(1)} KB)`;
        solutionSqlStatus.style.color = "#28a745";
        output.textContent = `✓ Solution SQL file loaded: ${f.name}`;
      } catch (err) {
        solutionSqlContent = "";
        solutionSqlStatus.textContent = "✗ Failed to load file";
        solutionSqlStatus.style.color = "#dc3545";
        output.textContent = `Failed to load solution SQL file: ${err}`;
      }
    });
  }

  // db file input handler (reads test_db.sql into memory)
  let dbSqlTextSample = "";
  let dbSqlTextEval = "";
  if (dbFileInputSample) {
    dbFileInputSample.addEventListener("change", async (e) => {
      const f = e.target.files[0];
      if (!f) return;
      dbSqlTextSample = await f.text();
      output.textContent = "Loaded Sample DB SQL file: " + (f.name || "db.sql");
    });
  }
  if (dbFileInputEval) {
    dbFileInputEval.addEventListener("change", async (e) => {
      const f = e.target.files[0];
      if (!f) return;
      dbSqlTextEval = await f.text();
      output.textContent = "Loaded Test DB SQL file: " + (f.name || "db.sql");
    });
  }

  // questions.pdf file input handler
  if (questionsPdfInput) {
    questionsPdfInput.addEventListener("change", async (e) => {
      const f = e.target.files[0];
      if (!f) {
        questionsPdfFile = null;
        pdfStatus.textContent = "";
        return;
      }
      questionsPdfFile = f;
      pdfStatus.textContent = `✓ ${f.name} loaded (${(f.size / 1024).toFixed(
        1
      )} KB)`;
      pdfStatus.style.color = "#28a745";
    });
  }

  // Parse Queries button - parses SQL and renders query items
  if (parseBtn) {
    parseBtn.addEventListener("click", async () => {
      if (!solutionSqlContent || !solutionSqlContent.trim()) {
        output.textContent = "Please select a solution.sql file first";
        return;
      }

      try {
        output.textContent = "Parsing queries from solution.sql...";
        const res = await fetch("/parse", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sql: solutionSqlContent }),
        });
        if (!res.ok) {
          const t = await res.text();
          output.textContent = `Parse failed: ${t}`;
          return;
        }
        const items = await res.json();

        if (items.length === 0) {
          output.textContent =
            "No valid SQL queries found (comments and empty lines are filtered out)";
          createBtn.disabled = true;
          return;
        }

        // Render parsed queries
        renderQueriesWithTypes(items);

        // Enable Create Tests button
        createBtn.disabled = false;

        output.textContent = `✓ Parsed ${items.length} queries successfully\n\nAdjust constraints and scores, then click "Create Tests"`;
      } catch (e) {
        output.textContent = `Parse request failed: ${e}`;
        createBtn.disabled = true;
      }
    });
  }

  // Create Tests button - sends queries to server to create tests
  if (createBtn) {
    createBtn.addEventListener("click", async () => {
      const common = getCommonCreds();
      const sampleCreds = {
        ...common,
        database: (dbNameSample?.value || "").trim(),
      };
      const evalCreds = {
        ...common,
        database: (dbNameEval?.value || "").trim(),
      };

      // Validate credentials before proceeding
      if (!common.user || !sampleCreds.database || !evalCreds.database) {
        output.textContent =
          "Please configure database credentials first (username and both database names required)";
        return;
      }

      // Collect test items from rendered queries
      const items = collectTestsObj();

      if (items.length === 0) {
        output.textContent =
          "No queries to create tests from. Please parse queries first.";
        return;
      }

      // Create object with queries and database credentials
      const payload = {
        queries: items,
        sample_db_credentials: sampleCreds,
        eval_db_credentials: evalCreds,
        allowed_after: allowedStartTime && allowedStartTime.value,
      };

      console.log("Sending create-tests payload:", {
        queriesCount: items.length,
        sample_db_credentials: { ...sampleCreds, password: "***" },
        eval_db_credentials: { ...evalCreds, password: "***" },
      });

      try {
        output.textContent =
          "Creating tests and building executable...\nThis may take a few minutes...";

        const res = await fetch("/create-tests", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        if (res.ok) {
          const data = await res.json();

          // Display test creation results
          let message = `✓ Tests created successfully!\n`;
          const evalCount = data.eval_tests
            ? Object.keys(data.eval_tests).length
            : 0;
          const sampleCount = data.sample_tests
            ? Object.keys(data.sample_tests).length
            : 0;
          const totalCount = Math.max(evalCount, sampleCount);
          message += `  ${totalCount} test cases generated\n\n`;

          // Display build status
          if (data.build_status) {
            if (data.build_status.success) {
              message += `✓ Student executable built successfully\n`;
              message += `  ${data.build_status.message}\n`;
              message += `  Ready for package download!\n`;
            } else {
              message += `⚠ Executable build failed:\n`;
              message += `  ${data.build_status.message}\n`;
              message += `  You can still create package without executable.\n`;
            }
          }

          output.textContent = message;

          // Show download package button after successful test creation
          if (packageRow) {
            packageRow.style.display = "flex";
          }
        } else {
          const text = await res.text();
          output.textContent = `Create-tests failed (status ${res.status}):\n${text}`;
        }
      } catch (e) {
        output.textContent = `Create-tests request failed: ${e}`;
      }
    });
  }

  // Clear button - resets everything
  clearBtn.addEventListener("click", () => {
    solutionSqlContent = "";
    if (solutionSqlInput) {
      solutionSqlInput.value = "";
    }
    if (solutionSqlStatus) {
      solutionSqlStatus.textContent = "";
    }
    queriesDiv.innerHTML = "";
    output.textContent = "";
    createBtn.disabled = true;
    if (packageRow) {
      packageRow.style.display = "none";
    }
  });

  // Close any open constraint dropdowns on outside click
  if (!window.__constraintsDropdownOutsideHandlerBound) {
    document.addEventListener("click", () => {
      document
        .querySelectorAll(".constraints-dropdown.open")
        .forEach((el) => el.classList.remove("open"));
    });
    window.__constraintsDropdownOutsideHandlerBound = true;
  }

  // Download Package button
  if (downloadPackageBtn) {
    downloadPackageBtn.addEventListener("click", async () => {
      try {
        output.textContent = "Creating student package...";

        // Get current database credentials
        const common = getCommonCreds();
        const sampleCreds = {
          ...common,
          database: (dbNameSample?.value || "").trim(),
        };
        const evalCreds = {
          ...common,
          database: (dbNameEval?.value || "").trim(),
        };

        // Create FormData and add the PDF if available
        const formData = new FormData();
        if (questionsPdfFile) {
          formData.append("questions_pdf", questionsPdfFile);
        }

        // Add database credentials as JSON
        formData.append(
          "db_credentials",
          JSON.stringify({
            sample_db_credentials: sampleCreds,
            eval_db_credentials: evalCreds,
          })
        );

        const res = await fetch("/create-package", {
          method: "POST",
          body: formData,
        });

        if (!res.ok) {
          const text = await res.text();
          output.textContent = `Package creation failed: ${text}`;
          return;
        }

        // Download the zip file
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "student_package.zip";
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        output.textContent =
          "Student package downloaded successfully!\nContains: questions.pdf (if provided), solution.sql (empty), sample_tests.json (plain), eval_tests.json.enc (encrypted), run_testcase executable, .env.local (with DB credentials)";
      } catch (e) {
        output.textContent = `Package download failed: ${e}`;
      }
    });
  }

  // Download list_scores executable button
  if (downloadListScoresBtn) {
    downloadListScoresBtn.addEventListener("click", async () => {
      try {
        output.textContent = "Downloading list_scores executable...";

        const res = await fetch("/download-list-scores", {
          method: "GET",
        });

        if (!res.ok) {
          const text = await res.text();
          output.textContent = `Download failed: ${text}`;
          return;
        }

        // Download the executable
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "list_scores";
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        output.textContent =
          "list_scores executable downloaded successfully!\nUse this to process student submission ZIPs and generate grades.xlsx";
      } catch (e) {
        output.textContent = `Download failed: ${e}`;
      }
    });
  }

  // remove download/copy/post buttons — server handles creation

  // Reset DB button: POST the DB creation SQL to the server which will run it
  if (resetDbBtnSample) {
    resetDbBtnSample.addEventListener("click", async () => {
      try {
        const common = getCommonCreds();
        const creds = {
          ...common,
          database: (dbNameSample?.value || "").trim(),
        };
        if (!creds.user || !creds.database) {
          output.textContent =
            "Please configure sample database credentials first (username and sample database name required)";
          return;
        }
        const payload = {
          sql: dbSqlTextSample || solutionSqlContent || "",
          db_credentials: creds,
        };
        if (!payload.sql) {
          output.textContent = "No Sample DB SQL provided. Load a script file.";
          return;
        }
        const res = await fetch("/reset-db", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const text = await res.text();
        output.textContent = "Reset Sample DB response:\n" + text;
      } catch (e) {
        output.textContent =
          "Reset Sample DB failed: " +
          e +
          "\n(Make sure run_server is running and mysql client is installed)";
      }
    });
  }
  if (resetDbBtnEval) {
    resetDbBtnEval.addEventListener("click", async () => {
      try {
        const common = getCommonCreds();
        const creds = { ...common, database: (dbNameEval?.value || "").trim() };
        if (!creds.user || !creds.database) {
          output.textContent =
            "Please configure test database credentials first (username and test database name required)";
          return;
        }
        const payload = {
          sql: dbSqlTextEval || solutionSqlContent || "",
          db_credentials: creds,
        };
        if (!payload.sql) {
          output.textContent = "No Test DB SQL provided. Load a script file.";
          return;
        }
        const res = await fetch("/reset-db", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const text = await res.text();
        output.textContent = "Reset Test DB response:\n" + text;
      } catch (e) {
        output.textContent =
          "Reset Test DB failed: " +
          e +
          "\n(Make sure run_server is running and mysql client is installed)";
      }
    });
  }

  function renderQueriesWithTypes(items) {
    queriesDiv.innerHTML = "";
    items.forEach((it, i) => {
      const q = it.query || it.sql || "";
      const type = it.type || it.query_type || analyzeQueryType(q);
      const wrap = document.createElement("div");
      wrap.className = "query-item";
      const label = document.createElement("div");
      label.textContent = `Q${i + 1}`;
      const ta = document.createElement("textarea");
      ta.value = q;
      ta.dataset.idx = i;

      const scoreWrap = document.createElement("div");
      scoreWrap.className = "score-wrap";
      const scoreLabel = document.createElement("label");
      scoreLabel.textContent = "Score:";
      scoreLabel.htmlFor = `q${i}-score`;
      const scoreInput = document.createElement("input");
      scoreInput.type = "number";
      scoreInput.min = "0";
      scoreInput.step = "0.5";
      scoreInput.value = it.score || 1;
      scoreInput.id = `q${i}-score`;
      scoreInput.className = "score-input";
      scoreWrap.appendChild(scoreLabel);
      scoreWrap.appendChild(scoreInput);

      const typeBadge = document.createElement("div");
      typeBadge.className = "query-type";
      typeBadge.textContent = type.toUpperCase();

      wrap.appendChild(label);
      wrap.appendChild(ta);
      wrap.appendChild(scoreWrap);
      wrap.appendChild(typeBadge);

      // constraints only for SELECT — now a multi-select dropdown
      if (type === "select") {
        const dd = document.createElement("div");
        dd.className = "constraints-dropdown";

        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "dropdown-toggle";
        toggle.setAttribute("aria-haspopup", "listbox");
        toggle.setAttribute("aria-expanded", "false");

        const menu = document.createElement("div");
        menu.className = "dropdown-menu";

        const constraintOptions = [
          { value: "require_join", label: "Require JOIN" },
          { value: "forbid_join", label: "Forbid JOIN" },
          { value: "require_nested_select", label: "Require nested SELECT" },
          { value: "forbid_nested_select", label: "Forbid nested SELECT" },
          { value: "require_group_by", label: "Require GROUP BY" },
          { value: "forbid_group_by", label: "Forbid GROUP BY" },
          { value: "require_order_by", label: "Require ORDER BY" },
          { value: "forbid_order_by", label: "Forbid ORDER BY" },
        ];

        // build checkbox list
        constraintOptions.forEach((opt) => {
          const row = document.createElement("label");
          row.className = "dropdown-option";
          const cb = document.createElement("input");
          cb.type = "checkbox";
          cb.value = opt.value;
          if (it[opt.value]) cb.checked = true;
          const span = document.createElement("span");
          span.textContent = opt.label;
          row.appendChild(cb);
          row.appendChild(span);
          menu.appendChild(row);
        });

        const hint = document.createElement("div");
        hint.className = "constraints-hint";
        hint.textContent = "Select one or more constraints.";
        menu.appendChild(hint);

        const updateToggleText = () => {
          const checked = menu.querySelectorAll(
            'input[type="checkbox"]:checked'
          );
          const count = checked.length;
          if (count === 0) {
            toggle.textContent = "Constraints: None";
          } else {
            const labels = Array.from(checked)
              .map((c) => c.parentElement.querySelector("span").textContent)
              .join(", ");
            toggle.textContent = `Constraints: ${labels}`;
          }
        };

        // initialize text and wire change handler
        updateToggleText();
        menu.addEventListener("change", updateToggleText);

        // toggle open/close
        toggle.addEventListener("click", (e) => {
          e.stopPropagation();
          const isOpen = dd.classList.toggle("open");
          toggle.setAttribute("aria-expanded", String(isOpen));
        });

        dd.appendChild(toggle);
        dd.appendChild(menu);
        wrap.appendChild(dd);
      } else if (type === "function") {
        // For CREATE FUNCTION: show input fields for test parameters
        const funcNote = document.createElement("div");
        funcNote.className = "function-test-inputs";
        funcNote.innerHTML = `<strong>Function Test Inputs</strong> <small>(one set of arguments per line, comma-separated)</small>`;
        const funcTextarea = document.createElement("textarea");
        funcTextarea.className = "function-inputs";
        funcTextarea.placeholder = "Example:\n1,2\n3,4\n'hello','world'";
        funcTextarea.rows = 3;
        funcTextarea.dataset.idx = i;
        funcNote.appendChild(funcTextarea);
        wrap.appendChild(funcNote);
      } else {
        const note = document.createElement("div");
        note.className = "constraint-note";
        note.textContent = "Constraints apply only to SELECT queries";
        wrap.appendChild(note);
      }

      queriesDiv.appendChild(wrap);
    });
  }

  function collectTestsObj() {
    // return array of test items
    const items = [];
    const nodes = queriesDiv.querySelectorAll(".query-item");
    nodes.forEach((node, idx) => {
      const ta = node.querySelector("textarea");
      const q = ta.value.trim();
      if (!q) return;
      const scoreInput = node.querySelector(".score-input");
      const score = scoreInput ? parseFloat(scoreInput.value) || 0 : 1;
      const typeBadge = node.querySelector(".query-type");
      const type = typeBadge
        ? typeBadge.textContent.toLowerCase()
        : analyzeQueryType(q);
      const obj = { query: q, type: type, score: score };
      // collect selected constraints from dropdown (if present)
      const menu = node.querySelector(".constraints-dropdown .dropdown-menu");
      if (menu) {
        menu
          .querySelectorAll('input[type="checkbox"]:checked')
          .forEach((cb) => {
            obj[cb.value] = true;
          });
      }

      // collect function test inputs if present
      const funcInputs = node.querySelector("textarea.function-inputs");
      if (funcInputs && funcInputs.value.trim()) {
        const lines = funcInputs.value.trim().split("\n");
        const testInputs = [];
        lines.forEach((line) => {
          const trimmed = line.trim();
          if (!trimmed) return;
          // parse comma-separated values
          // simple CSV parse: split by comma and trim; quoted strings get de-quoted
          const args = trimmed.split(",").map((arg) => {
            arg = arg.trim();
            // check if quoted string
            if (
              (arg.startsWith("'") && arg.endsWith("'")) ||
              (arg.startsWith('"') && arg.endsWith('"'))
            ) {
              return arg.slice(1, -1); // remove quotes
            }
            // check if number
            if (!isNaN(arg) && arg !== "") {
              return parseFloat(arg);
            }
            // else treat as string
            return arg;
          });
          testInputs.push(args);
        });
        if (testInputs.length > 0) {
          obj.test_inputs = testInputs;
        }
      }

      items.push(obj);
    });
    return items;
  }
});
