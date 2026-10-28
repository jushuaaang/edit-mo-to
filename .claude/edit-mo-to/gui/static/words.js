// Every word the app shows lives here. Joshua checks the Taglish.
// Labels stay English in both languages (spec "Beginner friendly", Language): buttons, tabs and filters, step names,
// status chips, field and column names, section titles, menu items. WORDS.labels lists them ("*" = a whole group);
// they have only an English line. Sentences (instructions and messages) have an English (en) and a Taglish (tl) line.
// Not here: Claude's own text (log lines, gate questions and options, outputs), the editor's text, file names, paths,
// prompts. Branding and the verse are fixed in index.html and never change.
//
//   t(key, vars)    the line for a dotted key ("why.timing") in the current language, {name} filled from vars; a label
//                   (no tl line) is English in both; the static test fails when a sentence has no tl line or a label
//                   has one; an unknown key shows itself
//   tEn(key, vars)  always English (to match what Claude wrote on the job card)
//   parts(key, vars) the line as pieces, a DOM node in place of each {name} given as a node
//   setLang(l) / getLang()  "en" | "tl" (Tagalog counts as Taglish); nextstep.js sets it from this computer's prefs
//   label(id, data) a short code on screen in words: SB-5 -> "Shot 5", CHAR-1 -> the character's name or "Character 1",
//                  V02 -> "Clip 2", P3 -> "Prompt 3"; anything else as it is. Files, targets and data-* keep the codes.
//   timeTitle(text) "2:12" or "0:00–2:12" in words (seconds:frames at 30 fps), or null when it is not a time
//
// WORDS between the two marker comments is plain JSON (tests read it): double quotes, no trailing commas.
/* WORDS-START */
export const WORDS = {
  "labels": {
    "step": "*",
    "word": "*",
    "state": "*",
    "tag": "*",
    "status": "*",
    "card": "*",
    "checks": "*",
    "table": "*",
    "set": ["path_root", "path_python", "path_tmp", "path_mcp", "path_drafts", "found", "missing", "port", "paths_h",
      "th_path", "th_value", "th_found"],
    "help": ["row"],
    "label": ["shot", "character", "clip", "prompt", "ai", "client"],
    "now": ["you", "claude", "none"],
    "alert": ["title_count"],
    "settings": ["alerts_h", "notify", "sound", "lang_h", "lang_auto", "lang_en", "lang_tl"],
    "practice": ["title", "copy", "start"],
    "page": ["why_label", "crumb"],
    "common": ["send", "save", "copy", "copied", "copy_failed", "close", "cancel", "done", "yes", "no", "none", "now",
      "sent_waiting", "claude_has_it"],
    "ui": ["pending"],
    "shell": ["skip", "nav_app", "dashboard", "settings", "title_settings", "steps_nav", "rail_toggle", "rail",
      "rail_close", "job_card", "activity", "tell"],
    "app": ["coming_title", "waits_for", "sr_done", "coming_h", "cant_open", "page_error"],
    "upload": ["add_files", "drop_files"],
    "gate": ["waiting", "waiting_title", "send_again", "drop_file"],
    "ask": ["history", "claude_says", "you_at", "title", "label"],
    "sp": ["saved_for_later", "already_answered", "capcut_closed", "change_cancelled", "early_h", "not_started"],
    "dash": ["in_progress", "temp_on", "timelines_one", "timelines", "step_now", "all_done", "progress",
      "older_check", "new_video", "recent", "none_h", "practice_h", "older", "practice_tag"],
    "fb": ["type", "bug", "suggest", "what", "no_step", "saved_h", "bug_chip", "suggestion_chip", "open_issue", "h",
      "title", "step", "send"],
    "storyboard": ["open_close", "picture_of", "drop", "comment_on", "char_title", "prev", "next", "prev_plain",
      "next_plain", "f_all", "f_need", "f_changed", "f_comments", "st_approved", "st_sent", "st_changed",
      "st_comment", "st_image", "st_client", "st_ready", "st_char", "char_sheet", "client_clip", "graphic", "ai",
      "client_footage", "comment", "copy_prompt", "replace", "character", "english_temp", "details",
      "comments_open_one", "comments_open", "not_approved_sent", "approved_waiting", "approve_all_sent",
      "approve_all", "approve_anyway", "wait_images", "view", "grid", "detail", "show", "share", "send_notes",
      "notes_h", "its_saved", "no_image", "save_prompt", "save_visual", "c_open", "send_comment", "comments",
      "visual", "kf_prompt", "request", "approve_shot", "shot", "choose_file"],
    "prompts": ["src_client", "src_ai", "src_both", "broll_source", "answered_storyboard", "generator", "site_model",
      "model", "other", "broll_h", "prompts_h"],
    "brief": ["link", "paste", "instructions", "refs", "style_h", "style", "script_lang", "not_set", "checklist_h",
      "th_rule", "th_source", "send_answers", "questions_h", "the_brief"],
    "build": ["sent", "choose", "st_working", "st_done", "st_error", "st_waiting", "st_skipped", "h", "project",
      "fix", "qa_h"],
    "captions": ["me", "claude", "auto_done", "timelines", "add", "tl_sent", "who"],
    "clips": ["folder", "pass", "flag", "contact", "check", "check_h"],
    "export": ["settings_h", "done_h", "learn", "review_learned"],
    "music": ["suno", "own", "source", "file", "suno_h"],
    "review": ["inplace", "new", "which", "all", "add", "send", "h", "item", "tl_unknown", "mode_new", "mode_inplace",
      "remove_label", "remove", "new_change", "timeline", "mode_label", "list_h", "done_h", "done"],
    "script": ["yours", "save", "line_label", "send", "lang", "temp_on", "th_id", "th_line", "th_en", "mine", "write"],
    "timing": ["keep", "rerecord", "w_cut", "w_review", "cut_label", "cut", "apply", "cuts_sent", "h"],
    "vo": ["lang_h", "files", "file_h", "reuse"],
    "dlg": ["link_ph", "will_create", "has_job", "found", "brief_link", "create", "cancel_change", "quit_check",
      "capcut_title", "project_word", "name_label", "later", "use_name", "name_title", "frames_of", "regen",
      "use_anyway", "choose_file", "transcribe", "timeline_pick", "use", "use_id", "older_vo", "use_sentences",
      "backup_where", "make_new", "change_inplace", "inplace_title", "where_keep", "general", "client_note",
      "saved_waiting", "declined", "decline", "learn_title"]
  },
  "en": {
    "step": {
      "brief": "Brief", "script": "Script", "storyboard": "Storyboard", "voiceover": "Voiceover",
      "timing": "Timing & cleanup", "prompts": "B-roll & prompts", "clips": "Clips", "build": "Build & QA",
      "review": "Review", "captions": "Captions", "music": "Music", "export": "Export"
    },
    "why": {
      "brief": "Claude reads the client's brief first, so every video follows their rules.",
      "script": "Claude writes the words the voice will say, following the brief.",
      "storyboard": "You see every shot as a picture before any video is made, so changes are quick and cheap.",
      "voiceover": "The recorded voice sets the timing of the whole video.",
      "timing": "Claude matches your voiceover to the script so cuts land on the words.",
      "prompts": "Claude writes a prompt for each extra shot, so you can make the clips.",
      "clips": "You make the video clips from the prompts. Claude checks each clip for problems.",
      "build": "Claude puts everything together in CapCut and checks the result.",
      "review": "You watch the video in CapCut and say what to change.",
      "captions": "Words on screen help people follow the video without sound.",
      "music": "Music sets the mood under the voice.",
      "export": "You save the finished videos from CapCut, ready to send."
    },
    "time": {
      "brief": "About 5 minutes.", "script": "About 5 minutes.",
      "storyboard": "About 20 minutes, mostly making the pictures.", "voiceover": "About 10 minutes.",
      "timing": "About 1 minute.", "prompts": "About 5 minutes.",
      "clips": "About 30 minutes, mostly making the clips.", "build": "About 10 minutes.",
      "review": "About 15 minutes.", "captions": "About 5 minutes.", "music": "About 5 minutes.",
      "export": "About 5 minutes."
    },
    "help": {
      "button": "What does {word} mean?", "row": "Words on this page:",
      "temp_en": "A temporary English track so you can follow a video in another language. Delete it before export.",
      "a_roll": "The main footage: the person talking to the camera.",
      "b_roll": "Extra shots that play over the voice, like the product or a close-up.",
      "keyframe": "A still picture of one shot. The video clip is made from it.",
      "timeline": "One version of the video in CapCut. Each hook gets its own timeline.",
      "vo": "Voiceover (VO): the recorded voice that reads the script.",
      "character_sheet": "One picture of a character from several sides, so they look the same in every shot.",
      "question": "Claude stops here and waits for your answer before it goes on.",
      "time": "Times are seconds:frames. 2:12 means 2 seconds and 12 frames (30 frames = 1 second).",
      "model": "The AI on Higgsfield that makes the clip. Each one has its own limits, like how long a clip can be.",
      "prompt": "The text you paste into the AI site to make a picture or a clip.",
      "time_value": "{s} seconds and {f} frames", "time_long": "{m} minutes, {s} seconds and {f} frames",
      "time_range": "{from} to {to}", "fps": "(30 frames = 1 second)"
    },
    "word": {
      "temp_en": "TEMP_EN", "a_roll": "A-roll", "b_roll": "B-roll", "keyframe": "keyframe", "timeline": "timeline",
      "vo": "voiceover", "character_sheet": "character sheet", "question": "Claude's question", "time": "the times",
      "model": "model", "prompt": "prompt"
    },
    "label": {
      "shot": "Shot {n}", "character": "Character {n}", "clip": "Clip {n}", "prompt": "Prompt {n}",
      "ai": "AI clip {n}", "client": "Client clip {n}", "two": "{a} and {b}", "many": "{rest} and {last}",
      "more": "{n} more"
    },
    "now": {
      "you": "You", "claude": "Claude", "none": "Status",
      "capcut": "Your turn: quit CapCut completely, then press “CapCut is closed” on the {step} page.",
      "pictures": "Your turn: make the pictures for {shots}, then drop each one on its card.",
      "pictures_question": "Your turn: make the pictures for {shots} and drop each one on its card, or answer Claude's question on the {step} page.",
      "voiceover": "Your turn: drop the voiceover file on the Voiceover page.",
      "question": "Your turn: answer Claude's question on the {step} page.",
      "answered": "You answered Claude's question on the {step} page. Claude picks it up next.",
      "waiting": "Your turn: the {step} page needs you.",
      "working": "Claude is working on {step}. Nothing to do yet.",
      "error": "Something went wrong in {step}. Tell Claude in the box below.",
      "error_card": "Something went wrong in {step}. Open it and tell Claude.", "done": "This video is finished.",
      "next": "Next: {step}. Claude starts it when it gets there.",
      "not_listening": "Claude isn't listening right now. Your answer is saved.",
      "not_listening_ask": "Claude isn't listening right now. You can still answer: it's saved until Claude checks."
    },
    "alert": {
      "notify_title": "Claude needs you: {step}", "title_count": "({n}) {title}"
    },
    "settings": {
      "alerts_h": "Tell me when Claude needs me",
      "alerts_p": "When Claude asks you something new, this computer can let you know. Saved on this computer only.",
      "notify": "Pop-up when Claude needs me",
      "notify_hint": "Your browser asks once if it may show pop-ups, the first time you click after Claude asks something.",
      "notify_blocked": "Your browser blocks pop-ups for this page. Allow them in the browser's site settings to get them.",
      "sound": "Sound", "sound_hint": "A short, soft sound.", "loading": "Loading…", "saved": "Saved.",
      "not_saved": "Not saved: {why}", "lang_h": "Language",
      "lang_p": "The words this app shows. Claude's messages, your script and your own text stay as they are.",
      "lang_auto": "Auto", "lang_en": "English", "lang_tl": "Taglish",
      "lang_auto_hint": "Auto follows the language you use with Claude. Now showing: {lang}.",
      "lang_manual_hint": "Claude's guess is not used while you pick a language here. Pick Auto to use it again."
    },
    "practice": {
      "title": "New here? Try a practice video first.",
      "what": "A 10-second practice video made from a clip of you talking. Same 12 steps as a real job, about 15 to 25 minutes, and no client sees it.",
      "type": "In Claude, type:", "copy": "Copy", "start": "Start practice", "starting": "Opening…",
      "opened": "Claude is opening in a new window. Send it your clip there.",
      "no_claude": "Claude isn't installed as a terminal command on this computer. Copy this and paste it into Claude instead.",
      "failed": "The window didn't open. Copy this and paste it into Claude instead.",
      "unsupported": "This computer can't open Claude from the app. Copy this and paste it into Claude instead.",
      "busy": "It's already opening. Wait a few seconds.",
      "mac_automation": "On a Mac, allow it in System Settings › Privacy & Security › Automation (let the app control Terminal), then press Start practice again."
    },
    "page": {
      "why_label": "Why this step", "crumb": "{name} · Step {n}"
    },
    "common": {
      "loading": "Loading…", "send": "Send", "save": "Save", "copy": "Copy", "copied": "Copied ✓",
      "copy_failed": "Copy failed", "close": "Close", "cancel": "Cancel", "done": "Done", "yes": "Yes", "no": "No",
      "none": "none", "now": "now", "checking": "Checking…", "nothing_yet": "Nothing yet.",
      "nothing_changed": "Nothing changed.", "not_sent": "Not sent. Try again.",
      "not_sent_moment": "Not sent. Try again in a moment.", "not_saved": "Not saved.",
      "not_saved_try": "Not saved. Try again.", "sent_listening": "Sent. Claude is listening.",
      "saved_later": "Saved. Claude reads it when it next checks.", "on_it": "Sent. Claude is on it.",
      "saved_waiting": "Saved, waiting for Claude", "sent_waiting": "Sent · waiting for Claude",
      "claude_has_it": "Claude has it"
    },
    "state": {
      "pending": "Not started", "working": "Claude working", "waiting": "Waiting on you", "done": "Done",
      "skipped": "Skipped", "error": "Error"
    },
    "tag": {
      "you": "You", "working": "Working", "error": "Error", "skipped": "Skipped", "optional": "Optional",
      "open": "Open now"
    },
    "ui": {
      "pending": "pending", "pending_title": "Saved. Claude hasn't applied it yet."
    },
    "status": {
      "ok": "OK", "wait": "Working", "you": "You", "err": "Check", "opt": "Optional", "mute": "Info"
    },
    "shell": {
      "skip": "Skip to the page", "nav_app": "App", "dashboard": "Dashboard", "settings": "Settings & setup",
      "title_settings": "Settings", "no_video": "No video open", "steps_nav": "Steps of this video",
      "connecting": "Connecting…", "rail_toggle": "Job & Claude", "rail": "Job and Claude",
      "rail_close": "Close the job panel", "job_card": "Job card", "activity": "Claude's activity",
      "tell": "Tell Claude anything", "tell_ph": "Tell Claude anything, about any step or the whole job…",
      "checking_listening": "Checking whether Claude is listening…", "whole_job": "Whole job · Ctrl+Enter"
    },
    "app": {
      "no_server": "The GUI server isn't answering. Is it still running?", "server_said": "The server said {status}.",
      "upload_refused": "The upload was refused ({status}).",
      "upload_stopped": "The upload stopped. Check the file type and size, then try again.",
      "open_first": "Open a video first.",
      "dialog_new_coming": "The New video form arrives in a later build. For now, start a new video with /edit-mo-to in Claude Code.",
      "dialog_coming": "This dialog arrives in a later build.", "coming_title": "Coming",
      "connected": "Connected · {host}", "not_connected": "Not connected · retrying",
      "key_h": "This page needs its key.",
      "key_p": "Open the link the server printed (it ends in ?k=…), or start the GUI again from Claude Code.",
      "waits_for": "Waits for: {step}", "sr_done": ", done",
      "open_to_see": "Open a video to see what Claude is doing.",
      "no_video_talk": "No video open. Open one on the Dashboard to talk to Claude about it.",
      "listening": "Claude is listening · {step}", "this_job": "this job",
      "listening_off": "Claude isn't listening. Your message is saved; it's picked up when Claude next checks, or type 'go' in chat. If Claude asked for permission, answer it in chat.",
      "open_on_dash": "Open a video on the Dashboard.",
      "err_404": "This folder has no job yet. It appears once /edit-mo-to starts it.",
      "err_403": "That folder isn't a video folder (a direct subfolder of the root).",
      "err_load": "This video could not be loaded.", "coming_h": "This page is coming",
      "coming_p": "The full {step} page arrives in a later build. Claude's questions for this step show above when it asks, and you can write to Claude below.",
      "coming_later": "It arrives in a later build.", "cant_open": "This video can't be opened",
      "page_error": "This page could not be shown"
    },
    "card": {
      "job": "Job", "client": "Client", "product": "Product", "style": "Style", "language": "Language",
      "temp_en": "TEMP_EN", "folder": "Folder", "vo": "VO", "generator": "Generator", "timelines": "Timelines",
      "project": "Project", "temp_on": "On · delete before export",
      "temp_partial": "On for {names} · delete before export", "temp_removed": "Removed", "temp_off": "Off",
      "not_set": "Not set", "not_yet": "Not yet"
    },
    "upload": {
      "kind": "This kind of file can't be added here.", "type": "{name}: that file type can't go here. Use {types}.",
      "big": "{name} is too big. The limit here is {limit}.", "empty": "{name} is empty.",
      "zone_label": "{label}: drop here or press Enter to choose", "add_files": "Add files",
      "drop_files": "Drop files here", "or_click": " or click to browse", "copied_to": "{types} · copied to",
      "copying": "Copying {name}…", "saved": "Saved {name}.", "not_finished": "The upload didn't finish."
    },
    "gate": {
      "waiting": "Waiting on you", "waiting_title": "Waiting on you: {title}",
      "stale": "That question closed; Claude asked something new", "not_counted": "Not counted: {answer}",
      "your_answer": "Your answer: {answer}", "send_again": "Send again", "drop_file": "Drop the file here"
    },
    "ask": {
      "history": "Earlier messages about this step", "claude_says": "Claude · {text}", "you_at": "You · {when}",
      "placeholder": "Anything about {step}…", "title": "Tell Claude about this step",
      "sub": "{step} · goes with your answers on this page", "label": "Message about {step}",
      "ctrl_enter": "Ctrl+Enter to send"
    },
    "checks": {
      "ok": "OK", "missing": "Missing", "title": "Setup check", "again": "Check again"
    },
    "table": {
      "status": "Status", "actions": "Actions", "empty": "Nothing here yet."
    },
    "sp": {
      "not_listening": "Claude isn't listening. Your answer is saved; it's picked up when Claude next checks, or type 'go' in chat.",
      "saved_early": "Saved for later. Claude asks you to confirm it when it gets to this step.",
      "saved_for_later": "Saved for later", "answer_above": "Answer it in Claude's question above.",
      "already_answered": "already answered", "capcut_closed": "CapCut is closed",
      "capcut_running": "CapCut is still running.", "capcut_check_failed": "Could not check CapCut. Try again.",
      "capcut_quit": "Quit CapCut completely before Claude writes", "change_cancelled": "Change cancelled",
      "output_unreadable": "Claude's {kind} output could not be read.", "early_h": "You can do this now",
      "early_p": "Claude hasn't reached this step yet. What you save here waits for it; when Claude gets here it asks you to confirm it instead of asking again.",
      "not_started": "Not started",
      "not_started_p": "Claude opens {step} when it gets here. You can still write to Claude about it below."
    },
    "dash": {
      "morning": "Good morning", "afternoon": "Good afternoon", "evening": "Good evening",
      "in_progress": "In progress", "temp_on": " (TEMP_EN on)", "timelines_one": "1 timeline",
      "timelines": "{n} timelines", "meta_none": "Style and language come from the brief",
      "step_now": "Step {n} · {what}", "all_done": "All steps done", "progress": "Progress",
      "older_check": "Older folders (no GUI history)", "looking": "Looking for your videos…",
      "new_video": "New video", "recent": "Recent activity",
      "sub_one": "1 video in progress · {waiting} waiting on you",
      "sub": "{active} videos in progress · {waiting} waiting on you", "none_h": "No videos in the GUI yet",
      "none_p": "Start one with /edit-mo-to in Claude Code. It shows here as soon as Claude creates the job.",
      "practice_h": "Practice", "older": "Started before the GUI ({n})", "practice_tag": " · practice"
    },
    "set": {
      "path_root": "Video folders (root)", "path_python": "Python (tools venv)", "path_tmp": "Work folder (tmp)",
      "path_mcp": "MCP servers folder", "path_drafts": "CapCut drafts folder",
      "saved_to": "Saved to {file} on this computer only.", "found": "found", "missing": "missing",
      "port": "GUI port",
      "running": "This server is running with root {root} on port {port}. Changed paths and the port apply the next time Claude opens the GUI (/edit-mo-to restarts this server with them).",
      "paths_h": "Paths", "th_path": "Path", "th_value": "Value", "th_found": "Found",
      "sub": "The paths this computer uses, the setup check, and a place to report bugs."
    },
    "fb": {
      "type": "Report type", "bug": "Report a bug", "suggest": "Suggest an improvement",
      "what": "What happened, or what would make the workflow better?", "no_step": "Not about one step",
      "saved_h": "Saved reports", "bug_chip": "Bug", "suggestion_chip": "Suggestion", "none": "Nothing saved yet.",
      "need": "Add a title and a few words first.", "saved_local": "Saved on this computer.",
      "issue_opened": "The issue page opened in your browser: check it and submit it there.",
      "blocked": "Your browser blocked the new tab.", "open_issue": "Open the issue page",
      "saved_file": "Saved on this computer (feedback.jsonl). Claude can read it when you say “look at my feedback”.",
      "h": "Report a bug / Suggest an improvement",
      "p": "Save keeps it on this computer. Send to Joshua also opens a pre-filled issue on GitHub that you check and submit yourself (a GitHub account is needed). Only what you type is included, plus the edit-mo-to version, Windows or macOS, and the step you pick. Nothing is sent automatically.",
      "title": "Title", "step": "Which step (optional)", "send": "Send to Joshua"
    },
    "storyboard": {
      "open_close": "Open {name} close up", "picture_of": "Picture of {name}", "drop": "Drop the picture for {name}",
      "comment_on": "Comment on {name}", "comment_what": "What should change in {name}?",
      "comment_dialog": "A comment on {name}…",
      "missing": "{n} shots have no keyframe yet ({names}). Approve anyway?",
      "missing_one": "1 shot has no keyframe yet ({names}). Approve anyway?",
      "char_title": "{name} · Character sheet", "save_as": "saved as storyboard/{id}.png, or choose a file",
      "prev": "← {name}", "next": "{name} →", "prev_plain": "← Previous", "next_plain": "Next →",
      "acted": "{word} {name}. {after}", "f_all": "All", "f_need": "Needs image", "f_changed": "Changed",
      "f_comments": "Comments", "no_prompt_yet": "prompt comes after the character sheet", "st_approved": "approved",
      "st_sent": "approval sent", "st_changed": "changed", "st_comment": "comment open", "st_image": "image added",
      "st_client": "client clip", "st_ready": "prompt ready", "st_char": "waiting for character sheet",
      "char_sheet": "Character sheet", "client_clip": "Client clip", "graphic": "Graphic", "ai": "AI",
      "client_footage": "Client footage", "no_keyframe_needed": "no keyframe needed", "comment": "Comment",
      "copy_prompt": "Copy prompt", "client_no_prompt": "The client's own footage: no prompt to copy.",
      "no_prompt_char": "Claude hasn't written this prompt yet.", "replace": "Replace image",
      "character": "Character", "english_temp": "English (temporary): {text}", "details": "Details",
      "comments_open_one": "1 comment open", "comments_open": "{n} comments open",
      "not_approved_sent": "Not approved · sent", "approved_waiting": "Approved · waiting for Claude",
      "approve_all_sent": "Approve all sent", "approve_all": "Approve all", "approve_anyway": "Approve anyway",
      "wait_images": "Wait for images", "view": "View", "grid": "Grid", "detail": "Detail", "show": "Show",
      "share": "Open share page", "notes_ph": "Anything about the whole board: pacing, look, the order of shots…",
      "send_notes": "Send notes", "notes_h": "Notes for the whole board", "its_saved": "It's saved",
      "empty_p": "Claude writes the shots here first (line, time, shot type and keyframe prompt); the images fill in after.",
      "no_match": "No cards match this filter.", "no_image": "No image yet", "save_prompt": "Save prompt",
      "save_visual": "Save visual direction", "c_open": "open", "send_comment": "Send comment",
      "comments": "Comments", "gone": "This shot is no longer on the board.", "visual": "Visual direction",
      "kf_prompt": "Keyframe prompt", "prompt_after": "The prompt comes after the character sheet.",
      "after_on": "Claude is on it.", "after_saved": "Saved, waiting for Claude.", "request": "Request change",
      "requested_for": "Change requested for", "approve_shot": "Approve shot", "approved_word": "Approved",
      "shot": "Shot", "choose_file": "Choose file"
    },
    "prompts": {
      "unknown_model": "We don't know this model's limits yet, so Claude uses safe settings: clips {min} to {max} seconds, up to {attach} pictures.",
      "unknown_model_plain": "We don't know this model's limits yet, so Claude uses safe settings.",
      "unverified": "Nobody has checked the limits of {model} yet. Claude checks the prompts and tells you if something may not fit.",
      "no_table": "The list of video sites couldn't be loaded. Ask Claude which site to use.",
      "regen": "{name}, to make it again in your video site", "src_client": "Client's B-roll",
      "src_ai": "Generate AI video", "src_both": "Both", "broll_source": "B-roll source",
      "answered_storyboard": "already answered at the storyboard", "generator": "Generator",
      "site_model": "{site} model", "model": "Model", "other": "Other",
      "no_prompt": "No prompt to copy (a client clip, or Claude hasn't written it yet).",
      "none_yet": "No prompts yet.", "broll_h": "B-roll", "prompts_h": "Prompts",
      "empty_p": "Claude writes the prompts per timeline here."
    },
    "brief": {
      "link": "Brief link (Notion or any URL)", "paste": "Or paste the brief",
      "paste_ph": "Paste the brief text here", "instructions": "Additional instructions",
      "instructions_ph": "Anything the brief doesn't say: must-haves, things to avoid, the client's wishes…",
      "refs": "Reference files (brief PDF or docx, reference videos, images)", "style_h": "Style and script language",
      "style": "Style", "style_none": "Claude picks it from the brief", "script_lang": "Script language",
      "not_set": "Not set yet", "checklist_h": "Brief checklist", "th_rule": "Rule", "th_source": "Source",
      "checklist_empty": "Claude writes the checklist after reading the brief.", "send_answers": "Send answers",
      "questions_h": "Claude's questions about the brief", "the_brief": "The brief"
    },
    "build": {
      "name_taken": "That project name is already taken in CapCut.", "sent": "Sent: {value}",
      "choose": "Choose another name", "st_working": "Claude is building", "st_done": "Built and checked",
      "st_error": "The build stopped with an error", "st_waiting": "Waiting on you", "st_skipped": "Skipped",
      "h": "Build", "project": "project", "fix": "Ask Claude to fix", "qa_h": "QA",
      "qa_empty": "QA results per timeline show here after the build."
    },
    "captions": {
      "me": "I'll run CapCut auto-caption", "claude": "Claude adds them", "temp_on": "TEMP_EN is still on.",
      "temp_p": "The TEMP_EN_delete_me track is only for review. Delete it before export; captions use the script's own words.",
      "me_p": "In CapCut: Text → Auto captions on each timeline, then pick a caption preset for an animated look.",
      "auto_done": "Auto-caption is done",
      "claude_p": "Simple text captions with the script's exact words and a pop-in; no word-by-word animation.",
      "timelines": "Timelines", "add": "Add captions", "tl_sent": "Timelines sent · waiting for Claude",
      "pick_one": "Pick at least one timeline.", "who": "Who adds the captions?"
    },
    "clips": {
      "folder": "Clips folder", "folder_hint": "The folder where you save the generated clips.", "pass": "PASS",
      "flag": "FLAG", "contact": "Contact sheet",
      "you_gen": "Generate the clips yourself in {gen} from the prompts on {step}, save them in the clips folder, then press Check clips.",
      "you": "Generate the clips yourself from the prompts on {step}, save them in the clips folder, then press Check clips.",
      "check": "Check clips", "check_h": "Clip check", "check_empty": "Results show here after Check clips."
    },
    "export": {
      "delete_h": "Delete the TEMP_EN_delete_me track before export", "still_on": "Still on: {names}",
      "card_says": "The job card says it is still on.",
      "cant_check_h": "Could not check: delete TEMP_EN_delete_me before export if present",
      "cant_check_err": "Couldn't check the project ({err}).",
      "no_project": "Couldn't check: no CapCut project on the job card yet.",
      "clean": "Checked the project: no TEMP_EN_delete_me track left.",
      "checking": "Checking the project for the TEMP_EN_delete_me track…",
      "no_drafts": "the CapCut drafts folder isn't set in Settings", "no_answer": "no answer",
      "unknown": "unknown error", "settings_h": "Export settings from the brief",
      "default": "Default: 9:16, 1080×1920, 30 fps.",
      "you": "Export each timeline in CapCut yourself, with the settings below.", "done_h": "Done exporting?",
      "done_p": "Claude then runs the learning step: it proposes preferences from this video, and you save or decline each.",
      "learn": "I've exported, run the learning step", "review_learned": "Review what Claude learned ({n})"
    },
    "music": {
      "suno": "Suno prompt from Claude", "own": "My own no-copyright track", "source": "Music source",
      "file": "Music file", "suno_h": "Suno prompt",
      "suno_p": "Parts of at most 18 s each; generate them in order and crossfade as the notes say.",
      "you_own": "Pick a no-copyright track (YouTube Audio Library or similar) and drop it here. It's copied to {where}",
      "you_suno": "Make the track in Suno with Claude's prompt, then drop the file here. It's copied to {where}"
    },
    "review": {
      "inplace": "In place (backup first)", "new": "New timeline",
      "ph": "What should change? e.g. “Hook 2: swap the 0:04 clip for the jar close-up”", "which": "Which timeline?",
      "all": "All timelines", "add": "Add to the list", "send": "Send changes", "h": "Your changes",
      "item": " · {timeline} · {mode}", "tl_unknown": "timeline?", "mode_new": "new timeline",
      "mode_inplace": "in place", "remove_label": "Remove change {n}", "remove": "Remove",
      "none": "No changes listed yet.", "new_change": "New change", "timeline": "Timeline",
      "mode_label": "In place or new timeline",
      "you": "Review the project in CapCut yourself. Edit it there, or list the changes here and Claude makes them.",
      "list_h": "Change list", "list_p": "Changes Claude is making show here.", "done_h": "All good?",
      "done_p": "When you're happy with every timeline, Claude moves on to captions.",
      "done": "I'm happy, go to captions"
    },
    "script": {
      "yours": "Your script", "ph": "Paste your script here, one line per row (hooks first, then the body).",
      "hint": "Claude uses it as written and only checks it against the brief.", "save": "Save my script",
      "empty": "Claude's script shows here once it's written.", "line_label": "Line {id}", "send": "Send edits",
      "lang": "Language: {lang}", "temp_on": "TEMP_EN on · delete before export", "th_id": "Id", "th_line": "Line",
      "th_en": "English (temporary)", "mine": "Use my script", "write": "Write one"
    },
    "timing": {
      "keep": "Keep", "rerecord": "Re-record", "w_cut": "Cut", "w_review": "Review", "cut_label": "Cut {id}",
      "cut": "cut", "apply": "Apply selected cuts", "cuts_sent": "Cuts sent · waiting for Claude",
      "h": "Line timings", "empty": "Claude times the voiceover after it's in."
    },
    "vo": {
      "lang_h": "Script language", "times_with": " · Claude times the VO with", "set_at_brief": "Set at the brief.",
      "you": "Make the voiceover yourself (ElevenLabs), as one file or one per hook/body, then drop it here. It's copied to {where}",
      "files": "Voiceover file(s)", "file_h": "Voiceover file", "reuse": "Reuse an older VO",
      "reuse_hint": "Saves credits: Claude transcribes an older VO and you pick the sentences."
    },
    "dlg": {
      "link_ph": "https://… (optional)", "goes_in": "Goes in {root}/", "will_create": "will be created",
      "has_job": "already has a job", "found": "found",
      "plain_name": "Use a plain folder name (no slashes, not starting with . or _). It goes directly in the video folders root.",
      "creating": "Creating…", "create_failed": "The video could not be created.",
      "new_p": "Claude starts the brief when you run /edit-mo-to on this folder in Claude Code.",
      "brief_link": "Brief link", "create": "Create video", "recheck": "Checking again every 2 seconds…",
      "still_running": "Still running (checked {time}). Checking again every 2 seconds…",
      "capcut_failed": "Could not check CapCut.",
      "capcut_p": "CapCut rewrites its projects when it closes, so a change written now would be lost. Quit CapCut completely (not just the window), then Claude writes.",
      "cancel_change": "Cancel this change", "quit_check": "I quit it, check again",
      "capcut_title": "CapCut is still running", "project_word": "Project",
      "name_exists": "A CapCut project with this name already exists.",
      "name_p": "Pick another name. Claude never overwrites an existing project.", "name_label": "New project name",
      "later": "Later", "use_name": "Use this name", "name_title": "Project name already taken",
      "frames_of": "Frames of {name}", "sheet_gone": "The contact sheet {name} can't be opened any more.",
      "no_sheet": "No contact sheet in this report. Claude can open it from the clip check folder.",
      "no_prompt_match": "No step-6 prompt matches this clip, so there is nothing to copy here.",
      "regen": "Mark for regenerate", "use_anyway": "Use anyway", "choose_file": "Choose a file you added…",
      "path_ph": "…or the full path of the older VO", "transcribe": "Ask Claude to transcribe it",
      "transcribe_saved": "Saved. The sentences show here once Claude has transcribed it.",
      "timeline_pick": "Timeline…", "use": "Use", "use_id": "Use {id}",
      "tick_first": "Tick the sentences to use first.",
      "oldvo_p": "Reuse a VO you already have instead of making a new one. Claude transcribes it, you tick the sentences to use and the timeline each one goes to.",
      "older_vo": "Older VO", "no_transcript": "No transcript yet.", "use_sentences": "Use these sentences",
      "backup_where": "edit-mo-to-backups/ in the CapCut project",
      "inplace_p": "Claude changes {names} in place. A backup of each timeline is saved first, in:",
      "the_timeline": "the timeline",
      "inplace_or": "Or keep the original untouched and Claude makes a new timeline with the change.",
      "make_new": "Make a new timeline", "change_inplace": "Change in place", "inplace_title": "Change in place?",
      "where_keep": "Where to keep {id}", "general": "General rule (my preferences)", "client_note": "Client note",
      "saved_waiting": "Saved · waiting for Claude", "declined": "Declined", "decline": "Decline",
      "learn_p": "Claude proposes these from this video. Save the ones that should shape the next videos; decline the rest.",
      "nothing_proposed": "Nothing proposed yet.", "learn_title": "Learning step"
    }
  },
  "tl": {
    "why": {
      "brief": "Babasahin muna ni Claude ang brief ng client, para sundin ng bawat video ang rules nila.",
      "script": "Isusulat ni Claude ang sasabihin ng boses, ayon sa brief.",
      "storyboard": "Makikita mo muna ang bawat shot bilang picture bago gawin ang video, kaya mabilis at tipid magbago.",
      "voiceover": "Ang recorded na boses ang nagse-set ng timing ng buong video.",
      "timing": "Itutugma ni Claude ang voiceover mo sa script para tumama ang cuts sa mga salita.",
      "prompts": "Gagawa si Claude ng prompt para sa bawat extra shot, para magawa mo ang clips.",
      "clips": "Ikaw ang gagawa ng video clips mula sa prompts. Iche-check ni Claude ang bawat clip kung may problema.",
      "build": "Pagsasamahin ni Claude ang lahat sa CapCut at iche-check ang resulta.",
      "review": "Panoorin mo ang video sa CapCut at sabihin kung ano ang babaguhin.",
      "captions": "Ang words sa screen ay tumutulong sa mga nanonood nang walang sound.",
      "music": "Ang music ang nagse-set ng mood sa ilalim ng boses.",
      "export": "I-save mo ang tapos na videos mula sa CapCut, ready nang ipadala."
    },
    "time": {
      "brief": "Mga 5 minuto.", "script": "Mga 5 minuto.",
      "storyboard": "Mga 20 minuto, karamihan sa paggawa ng pictures.", "voiceover": "Mga 10 minuto.",
      "timing": "Mga 1 minuto.", "prompts": "Mga 5 minuto.", "clips": "Mga 30 minuto, karamihan sa paggawa ng clips.",
      "build": "Mga 10 minuto.", "review": "Mga 15 minuto.", "captions": "Mga 5 minuto.", "music": "Mga 5 minuto.",
      "export": "Mga 5 minuto."
    },
    "help": {
      "button": "Ano ang ibig sabihin ng {word}?",
      "temp_en": "Pansamantalang English track para masundan mo ang video na nasa ibang language. Burahin ito bago mag-export.",
      "a_roll": "Ang main footage: ang taong nagsasalita sa camera.",
      "b_roll": "Extra shots na lumalabas habang nagsasalita ang boses, tulad ng product o close-up.",
      "keyframe": "Isang still picture ng isang shot. Dito gagawin ang video clip.",
      "timeline": "Isang version ng video sa CapCut. May sariling timeline ang bawat hook.",
      "vo": "Voiceover (VO): ang recorded na boses na nagbabasa ng script.",
      "character_sheet": "Isang picture ng character mula sa iba't ibang side, para pareho ang itsura niya sa bawat shot.",
      "question": "Dito titigil si Claude at hihintayin ang sagot mo bago magtuloy.",
      "time": "Ang times ay seconds:frames. Ang 2:12 ay 2 segundo at 12 frames (30 frames = 1 segundo).",
      "model": "Ang AI sa Higgsfield na gumagawa ng clip. May sariling limits ang bawat isa, tulad ng haba ng clip.",
      "prompt": "Ang text na ipe-paste mo sa AI site para gumawa ng picture o clip.",
      "time_value": "{s} segundo at {f} frames", "time_long": "{m} minuto, {s} segundo at {f} frames",
      "time_range": "{from} hanggang {to}", "fps": "(30 frames = 1 segundo)"
    },
    "label": {
      "two": "{a} at {b}", "many": "{rest} at {last}", "more": "{n} pa"
    },
    "now": {
      "capcut": "Ikaw na: i-quit nang buo ang CapCut, tapos pindutin ang “CapCut is closed” sa {step} page.",
      "pictures": "Ikaw na: gawin ang pictures ng {shots}, tapos i-drop ang bawat isa sa card nito.",
      "pictures_question": "Ikaw na: gawin ang pictures ng {shots} at i-drop ang bawat isa sa card nito, o sagutin ang tanong ni Claude sa {step} page.",
      "voiceover": "Ikaw na: i-drop ang voiceover file sa Voiceover page.",
      "question": "Ikaw na: sagutin ang tanong ni Claude sa {step} page.",
      "answered": "Nasagot mo na ang tanong ni Claude sa {step} page. Si Claude na ang susunod.",
      "waiting": "Ikaw na: kailangan ka sa {step} page.",
      "working": "Si Claude ang gumagawa ng {step}. Wala ka pang gagawin.",
      "error": "May nagka-problema sa {step}. Sabihin kay Claude sa box sa ibaba.",
      "error_card": "May nagka-problema sa {step}. Buksan ito at sabihin kay Claude.",
      "done": "Tapos na ang video na ito.", "next": "Susunod: {step}. Sisimulan ito ni Claude pagdating doon.",
      "not_listening": "Hindi nakikinig si Claude ngayon. Naka-save ang sagot mo.",
      "not_listening_ask": "Hindi nakikinig si Claude ngayon. Pwede ka pa ring sumagot: naka-save ito hanggang mag-check si Claude."
    },
    "alert": {
      "notify_title": "Kailangan ka ni Claude: {step}"
    },
    "settings": {
      "alerts_p": "Kapag may bagong tanong si Claude, sasabihan ka ng computer na ito. Naka-save sa computer na ito lang.",
      "notify_hint": "Isang beses magtatanong ang browser mo kung pwedeng mag-pop-up, sa unang click mo pagkatapos magtanong ni Claude.",
      "notify_blocked": "Naka-block ang pop-ups sa page na ito. I-allow sila sa site settings ng browser mo.",
      "sound_hint": "Maikli at mahinang tunog.", "loading": "Naglo-load…", "saved": "Na-save.",
      "not_saved": "Hindi na-save: {why}",
      "lang_p": "Ang mga salitang pinapakita ng app. Hindi binabago ang messages ni Claude, ang script, at ang sarili mong text.",
      "lang_auto_hint": "Sinusundan ng Auto ang language na gamit mo kay Claude. Ngayon: {lang}.",
      "lang_manual_hint": "Hindi sinusunod ang hula ni Claude habang may pinili ka rito. Piliin ang Auto para gamitin ulit."
    },
    "practice": {
      "what": "Isang 10-second practice video mula sa clip mo habang nagsasalita. Parehong 12 steps ng totoong job, mga 15 hanggang 25 minuto, at walang client na makakakita.",
      "type": "Sa Claude, i-type:", "starting": "Binubuksan…",
      "opened": "Bubukas si Claude sa bagong window. Doon mo i-send ang clip mo.",
      "no_claude": "Hindi naka-install si Claude bilang terminal command sa computer na ito. I-copy na lang ito at i-paste kay Claude.",
      "failed": "Hindi bumukas ang window. I-copy na lang ito at i-paste kay Claude.",
      "unsupported": "Hindi kayang buksan si Claude mula sa app sa computer na ito. I-copy na lang ito at i-paste kay Claude.",
      "busy": "Binubuksan na. Maghintay ng ilang segundo.",
      "mac_automation": "Sa Mac, i-allow ito sa System Settings › Privacy & Security › Automation (payagan ang app na i-control ang Terminal), tapos pindutin ulit ang Start practice."
    },
    "common": {
      "loading": "Naglo-load…", "checking": "Chine-check…", "nothing_yet": "Wala pa.",
      "nothing_changed": "Walang binago.", "not_sent": "Hindi na-send. Subukan ulit.",
      "not_sent_moment": "Hindi na-send. Subukan ulit maya-maya.", "not_saved": "Hindi na-save.",
      "not_saved_try": "Hindi na-save. Subukan ulit.", "sent_listening": "Na-send. Nakikinig si Claude.",
      "saved_later": "Na-save. Babasahin ito ni Claude sa susunod niyang check.",
      "on_it": "Na-send. Ginagawa na ni Claude.", "saved_waiting": "Na-save, hinihintay si Claude"
    },
    "ui": {
      "pending_title": "Na-save. Hindi pa ito nagagawa ni Claude."
    },
    "shell": {
      "no_video": "Walang nakabukas na video", "connecting": "Kumokonekta…",
      "tell_ph": "Sabihin kay Claude kahit ano, tungkol sa kahit anong step o sa buong job…",
      "checking_listening": "Chine-check kung nakikinig si Claude…", "whole_job": "Buong job · Ctrl+Enter"
    },
    "app": {
      "no_server": "Hindi sumasagot ang server ng app. Tumatakbo pa ba ito?",
      "server_said": "Sabi ng server: {status}.", "upload_refused": "Hindi tinanggap ang upload ({status}).",
      "upload_stopped": "Huminto ang upload. I-check ang file type at size, tapos subukan ulit.",
      "open_first": "Magbukas muna ng video.",
      "dialog_new_coming": "Darating ang New video form sa susunod na build. Sa ngayon, magsimula ng bagong video gamit ang /edit-mo-to sa Claude Code.",
      "dialog_coming": "Darating ang dialog na ito sa susunod na build.", "connected": "Connected · {host}",
      "not_connected": "Hindi connected · sinusubukan ulit", "key_h": "Kailangan ng page na ito ang key nito.",
      "key_p": "Buksan ang link na ni-print ng server (nagtatapos sa ?k=…), o simulan ulit ang app mula sa Claude Code.",
      "open_to_see": "Magbukas ng video para makita ang ginagawa ni Claude.",
      "no_video_talk": "Walang nakabukas na video. Magbukas sa Dashboard para makausap si Claude tungkol dito.",
      "listening": "Nakikinig si Claude · {step}", "this_job": "ang job na ito",
      "listening_off": "Hindi nakikinig si Claude. Naka-save ang message mo; babasahin ito sa susunod na check ni Claude, o i-type ang 'go' sa chat. Kung humingi si Claude ng permission, sagutin ito sa chat.",
      "open_on_dash": "Magbukas ng video sa Dashboard.",
      "err_404": "Wala pang job ang folder na ito. Lalabas ito kapag sinimulan na ng /edit-mo-to.",
      "err_403": "Hindi video folder iyan (dapat direktang subfolder ng root).",
      "err_load": "Hindi ma-load ang video na ito.",
      "coming_p": "Darating ang buong {step} page sa susunod na build. Lalabas sa itaas ang mga tanong ni Claude para sa step na ito, at pwede kang sumulat kay Claude sa ibaba.",
      "coming_later": "Darating ito sa susunod na build."
    },
    "upload": {
      "kind": "Hindi pwedeng idagdag dito ang ganitong file.",
      "type": "{name}: hindi pwede rito ang file type na iyan. Gamitin ang {types}.",
      "big": "Masyadong malaki ang {name}. Ang limit dito ay {limit}.", "empty": "Walang laman ang {name}.",
      "zone_label": "{label}: i-drop dito o pindutin ang Enter para pumili", "or_click": " o i-click para pumili",
      "copied_to": "{types} · kokopyahin sa", "copying": "Kinokopya ang {name}…", "saved": "Na-save ang {name}.",
      "not_finished": "Hindi natapos ang upload."
    },
    "gate": {
      "stale": "Sarado na ang tanong na iyan; may bagong tanong si Claude", "not_counted": "Hindi binilang: {answer}",
      "your_answer": "Sagot mo: {answer}"
    },
    "ask": {
      "placeholder": "Kahit ano tungkol sa {step}…", "sub": "{step} · kasama ng mga sagot mo sa page na ito",
      "ctrl_enter": "Ctrl+Enter para i-send"
    },
    "sp": {
      "not_listening": "Hindi nakikinig si Claude. Naka-save ang sagot mo; babasahin ito sa susunod na check ni Claude, o i-type ang 'go' sa chat.",
      "saved_early": "Naka-save para mamaya. Ipapa-confirm ito sa iyo ni Claude pagdating sa step na ito.",
      "answer_above": "Sagutin ito sa tanong ni Claude sa itaas.", "capcut_running": "Bukas pa ang CapCut.",
      "capcut_check_failed": "Hindi ma-check ang CapCut. Subukan ulit.",
      "capcut_quit": "I-quit nang buo ang CapCut bago magsulat si Claude",
      "output_unreadable": "Hindi mabasa ang {kind} output ni Claude.",
      "early_p": "Hindi pa umaabot si Claude sa step na ito. Maghihintay dito ang ise-save mo; pagdating ni Claude, ipapa-confirm na lang niya ito sa iyo imbes na magtanong ulit.",
      "not_started_p": "Bubuksan ni Claude ang {step} pagdating dito. Pwede ka pa ring sumulat kay Claude tungkol dito sa ibaba."
    },
    "dash": {
      "morning": "Magandang umaga", "afternoon": "Magandang hapon", "evening": "Magandang gabi",
      "meta_none": "Sa brief manggagaling ang style at language", "looking": "Hinahanap ang videos mo…",
      "sub_one": "1 video ang ginagawa · {waiting} ang naghihintay sa iyo",
      "sub": "{active} videos ang ginagawa · {waiting} ang naghihintay sa iyo",
      "none_p": "Magsimula gamit ang /edit-mo-to sa Claude Code. Lalabas ito rito pagkagawa ni Claude ng job."
    },
    "set": {
      "saved_to": "Naka-save sa {file} sa computer na ito lang.",
      "running": "Tumatakbo ang server na ito sa root {root}, port {port}. Ang binagong paths at port ay gagana sa susunod na buksan ni Claude ang app (ire-restart ng /edit-mo-to ang server gamit ang mga ito).",
      "sub": "Ang paths na gamit ng computer na ito, ang setup check, at lugar para mag-report ng bugs."
    },
    "fb": {
      "none": "Wala pang naka-save.", "need": "Maglagay muna ng title at ilang salita.",
      "saved_local": "Naka-save sa computer na ito.",
      "issue_opened": "Bumukas ang issue page sa browser mo: i-check ito at i-submit doon.",
      "blocked": "Na-block ng browser mo ang bagong tab.",
      "saved_file": "Naka-save sa computer na ito (feedback.jsonl). Mababasa ito ni Claude kapag sinabi mong “look at my feedback”.",
      "p": "Ang Save ay nagtatabi nito sa computer na ito. Ang Send to Joshua ay magbubukas din ng naka-fill na issue sa GitHub na iche-check at isa-submit mo mismo (kailangan ng GitHub account). Kasama lang ang tina-type mo, ang edit-mo-to version, Windows o macOS, at ang step na pipiliin mo. Walang naipapadala nang kusa."
    },
    "storyboard": {
      "comment_what": "Ano ang babaguhin sa {name}?", "comment_dialog": "Comment sa {name}…",
      "missing": "{n} shots ang wala pang keyframe ({names}). I-approve pa rin?",
      "missing_one": "1 shot ang wala pang keyframe ({names}). I-approve pa rin?",
      "save_as": "ise-save bilang storyboard/{id}.png, o pumili ng file", "acted": "{word} {name}. {after}",
      "no_prompt_yet": "susunod ang prompt pagkatapos ng character sheet",
      "no_keyframe_needed": "hindi kailangan ng keyframe",
      "client_no_prompt": "Sariling footage ng client: walang prompt na ico-copy.",
      "no_prompt_char": "Hindi pa naisusulat ni Claude ang prompt na ito.",
      "notes_ph": "Kahit ano tungkol sa buong board: pacing, itsura, pagkakasunod ng shots…",
      "empty_p": "Dito muna isusulat ni Claude ang shots (line, time, shot type at keyframe prompt); susunod ang images.",
      "no_match": "Walang card na tugma sa filter na ito.", "gone": "Wala na sa board ang shot na ito.",
      "prompt_after": "Susunod ang prompt pagkatapos ng character sheet.", "after_on": "Ginagawa na ni Claude.",
      "after_saved": "Na-save, hinihintay si Claude.", "requested_for": "Humingi ng pagbabago sa",
      "approved_word": "Na-approve ang"
    },
    "prompts": {
      "unknown_model": "Hindi pa namin alam ang limits ng model na ito, kaya safe settings ang gamit ni Claude: clips na {min} hanggang {max} segundo, hanggang {attach} pictures.",
      "unknown_model_plain": "Hindi pa namin alam ang limits ng model na ito, kaya safe settings ang gamit ni Claude.",
      "unverified": "Wala pang nag-check ng limits ng {model}. Iche-check ni Claude ang prompts at sasabihan ka kung may hindi kakasya.",
      "no_table": "Hindi ma-load ang listahan ng video sites. Tanungin si Claude kung aling site ang gagamitin.",
      "regen": "{name}, para gawin ulit sa video site mo",
      "no_prompt": "Walang prompt na ico-copy (client clip ito, o hindi pa ito naisusulat ni Claude).",
      "none_yet": "Wala pang prompts.", "empty_p": "Dito isusulat ni Claude ang prompts sa bawat timeline."
    },
    "brief": {
      "paste_ph": "I-paste dito ang text ng brief",
      "instructions_ph": "Kahit anong wala sa brief: dapat meron, dapat iwasan, gusto ng client…",
      "style_none": "Pipiliin ni Claude mula sa brief",
      "checklist_empty": "Isusulat ni Claude ang checklist pagkabasa ng brief."
    },
    "build": {
      "name_taken": "May project na sa CapCut na ganyan ang pangalan.",
      "qa_empty": "Lalabas dito ang QA results ng bawat timeline pagkatapos ng build."
    },
    "captions": {
      "temp_on": "Naka-on pa ang TEMP_EN.",
      "temp_p": "Pang-review lang ang TEMP_EN_delete_me track. Burahin ito bago mag-export; ang captions ay galing sa mismong words ng script.",
      "me_p": "Sa CapCut: Text → Auto captions sa bawat timeline, tapos pumili ng caption preset para may animation.",
      "claude_p": "Simpleng text captions na eksaktong words ng script, may pop-in; walang word-by-word animation.",
      "pick_one": "Pumili ng kahit isang timeline."
    },
    "clips": {
      "folder_hint": "Ang folder kung saan mo sine-save ang ginawang clips.",
      "you_gen": "Ikaw ang gagawa ng clips sa {gen} mula sa prompts sa {step}, i-save sa clips folder, tapos pindutin ang Check clips.",
      "you": "Ikaw ang gagawa ng clips mula sa prompts sa {step}, i-save sa clips folder, tapos pindutin ang Check clips.",
      "check_empty": "Lalabas dito ang resulta pagkatapos ng Check clips."
    },
    "export": {
      "delete_h": "Burahin ang TEMP_EN_delete_me track bago mag-export", "still_on": "Naka-on pa sa: {names}",
      "card_says": "Sabi ng job card, naka-on pa ito.",
      "cant_check_h": "Hindi ma-check: burahin ang TEMP_EN_delete_me bago mag-export kung meron pa",
      "cant_check_err": "Hindi ma-check ang project ({err}).",
      "no_project": "Hindi ma-check: wala pang CapCut project sa job card.",
      "clean": "Na-check ang project: wala nang TEMP_EN_delete_me track.",
      "checking": "Chine-check ang project kung may TEMP_EN_delete_me track…",
      "no_drafts": "wala pang CapCut drafts folder sa Settings", "no_answer": "walang sagot",
      "unknown": "hindi alam na error", "default": "Default: 9:16, 1080×1920, 30 fps.",
      "you": "Ikaw ang mag-e-export ng bawat timeline sa CapCut, gamit ang settings sa ibaba.",
      "done_p": "Susunod, gagawin ni Claude ang learning step: magmumungkahi siya ng preferences mula sa video na ito, at ise-save o ide-decline mo ang bawat isa."
    },
    "music": {
      "suno_p": "Mga part na hanggang 18 s bawat isa; gawin nang sunod-sunod at i-crossfade ayon sa notes.",
      "you_own": "Pumili ng no-copyright track (YouTube Audio Library o katulad) at i-drop dito. Kokopyahin ito sa {where}",
      "you_suno": "Gawin ang track sa Suno gamit ang prompt ni Claude, tapos i-drop dito ang file. Kokopyahin ito sa {where}"
    },
    "review": {
      "ph": "Ano ang babaguhin? hal. “Hook 2: palitan ang clip sa 0:04 ng close-up ng jar”",
      "none": "Wala pang nakalistang changes.",
      "you": "I-review mo ang project sa CapCut. I-edit doon, o ilista dito ang changes at si Claude ang gagawa.",
      "list_p": "Lalabas dito ang changes na ginagawa ni Claude.",
      "done_p": "Kapag okay ka na sa bawat timeline, lilipat si Claude sa captions."
    },
    "script": {
      "ph": "I-paste dito ang script mo, isang line bawat row (hooks muna, tapos ang body).",
      "hint": "Gagamitin ito ni Claude nang ganyan mismo at iche-check lang laban sa brief.",
      "empty": "Lalabas dito ang script ni Claude kapag naisulat na."
    },
    "timing": {
      "empty": "Ita-time ni Claude ang voiceover pagdating nito."
    },
    "vo": {
      "times_with": " · Ita-time ni Claude ang VO gamit ang", "set_at_brief": "Nase-set sa brief.",
      "you": "Ikaw ang gagawa ng voiceover (ElevenLabs), isang file o isa bawat hook/body, tapos i-drop dito. Kokopyahin ito sa {where}",
      "reuse_hint": "Tipid sa credits: ita-transcribe ni Claude ang lumang VO at ikaw ang pipili ng sentences."
    },
    "dlg": {
      "goes_in": "Mapupunta sa {root}/",
      "plain_name": "Gumamit ng simpleng folder name (walang slash, hindi nagsisimula sa . o _). Diretso ito sa video folders root.",
      "creating": "Ginagawa…", "create_failed": "Hindi nagawa ang video.",
      "new_p": "Sisimulan ni Claude ang brief kapag pinatakbo mo ang /edit-mo-to sa folder na ito sa Claude Code.",
      "recheck": "Chine-check ulit kada 2 segundo…",
      "still_running": "Bukas pa (na-check {time}). Chine-check ulit kada 2 segundo…",
      "capcut_failed": "Hindi ma-check ang CapCut.",
      "capcut_p": "Isinusulat ulit ng CapCut ang projects nito pagsara, kaya mawawala ang change na isusulat ngayon. I-quit nang buo ang CapCut (hindi lang ang window), tapos magsusulat si Claude.",
      "name_exists": "May CapCut project na sa pangalang ito.",
      "name_p": "Pumili ng ibang pangalan. Hindi kailanman papatungan ni Claude ang existing na project.",
      "sheet_gone": "Hindi na mabuksan ang contact sheet na {name}.",
      "no_sheet": "Walang contact sheet sa report na ito. Mabubuksan ito ni Claude mula sa clip check folder.",
      "no_prompt_match": "Walang prompt sa step 6 na tugma sa clip na ito, kaya walang ico-copy dito.",
      "path_ph": "…o ang buong path ng lumang VO",
      "transcribe_saved": "Na-save. Lalabas dito ang sentences kapag na-transcribe na ni Claude.",
      "tick_first": "I-tick muna ang sentences na gagamitin.",
      "oldvo_p": "Gamitin ulit ang VO na meron ka na imbes na gumawa ng bago. Ita-transcribe ito ni Claude, ikaw ang magti-tick ng sentences na gagamitin at kung saang timeline mapupunta ang bawat isa.",
      "no_transcript": "Wala pang transcript.",
      "inplace_p": "Babaguhin ni Claude ang {names} sa mismong timeline. May backup muna ang bawat timeline, sa:",
      "the_timeline": "ang timeline",
      "inplace_or": "O hayaan ang original at gagawa si Claude ng bagong timeline na may change.",
      "learn_p": "Mungkahi ito ni Claude mula sa video na ito. I-save ang mga dapat sundin sa susunod na videos; i-decline ang iba.",
      "nothing_proposed": "Wala pang mungkahi."
    }
  }
};
/* WORDS-END */

let lang = "en";

/** "en" or "tl"; true when it changed. */
export function setLang(next) {
  const l = next === "tl" ? "tl" : "en";
  if (l === lang) return false;
  lang = l;
  return true;
}
export const getLang = () => lang;

const at = (dict, key) => key.split(".").reduce((o, k) => (o && typeof o === "object" ? o[k] : undefined), dict);
const fill = (s, vars) => s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] === undefined || vars[k] === null ? m : String(vars[k])));

/** The line for `key` in the current language with {name} filled from vars. A missing key shows the key, never blank. */
export function t(key, vars = {}) {
  let s = at(WORDS[lang], key);
  if (typeof s !== "string") s = at(WORDS.en, key);
  return typeof s === "string" ? fill(s, vars) : key;
}

/** The English line, whatever the language (for matching what Claude wrote). */
export function tEn(key, vars = {}) {
  const s = at(WORDS.en, key);
  return typeof s === "string" ? fill(s, vars) : key;
}

/** The line split into pieces for h(): text, and a Node where vars[name] is a Node ("Saved to {file} …"). */
export function parts(key, vars = {}) {
  const nodes = Object.fromEntries(Object.entries(vars).filter(([, v]) => v instanceof Node));
  const text = t(key, Object.fromEntries(Object.entries(vars).filter(([k]) => !(k in nodes))));
  return text.split(/(\{\w+\})/).filter(Boolean).map((piece) => {
    const m = /^\{(\w+)\}$/.exec(piece);
    return m && nodes[m[1]] ? nodes[m[1]] : piece;
  });
}

const LIST_MAX = 4;  // longer lists end "… and 3 more"

/** "Shot 5", "Shot 5 and Shot 6", "Shot 5, Shot 6 and Shot 8", "Shot 1, Shot 2, Shot 3 and 9 more". */
export function listText(names) {
  if (names.length > LIST_MAX) {
    const shown = names.slice(0, LIST_MAX - 1);
    return t("label.many", { rest: shown.join(", "), last: t("label.more", { n: names.length - shown.length }) });
  }
  if (names.length <= 1) return names[0] || "";
  if (names.length === 2) return t("label.two", { a: names[0], b: names[1] });
  return t("label.many", { rest: names.slice(0, -1).join(", "), last: names[names.length - 1] });
}

const CODES = [
  [/^SB-(\d+)$/i, "label.shot"], [/^CHAR-(\d+)$/i, "label.character"], [/^V0*(\d+)$/i, "label.clip"],
  [/^P0*(\d+)$/i, "label.prompt"], [/^AI-0*(\d+)$/i, "label.ai"], [/^C-0*(\d+)$/i, "label.client"],
];

/** A code in words. CHAR-n uses the character's name from storyboard.json when known (the part before a comma). */
export function label(id, data) {
  const s = String(id ?? "").trim();
  if (/^CHAR-\d+$/i.test(s)) {
    const c = (Array.isArray(data?.storyboard?.characters) ? data.storyboard.characters : []).find((x) => x?.id === s);
    const name = typeof c?.name === "string" ? c.name.split(",")[0].trim() : "";
    if (name) return name;
  }
  for (const [re, key] of CODES) {
    const m = re.exec(s);
    if (m) return t(key, { n: Number(m[1]) });
  }
  return s;
}

const ONE = /^(\d+):(\d{2})(?::(\d{2}))?$/;

function oneTime(s) {
  const m = ONE.exec(s.trim());
  if (!m) return null;
  return m[3] === undefined ? t("help.time_value", { s: Number(m[1]), f: Number(m[2]) })
    : t("help.time_long", { m: Number(m[1]), s: Number(m[2]), f: Number(m[3]) });
}

/** "2:12" in words ("2 seconds and 12 frames", then the help.fps note); a range "0:00–2:12" reads "… to …". Else null. */
export function timeTitle(text) {
  const parts2 = String(text ?? "").split(/\s*[–-]\s*/);
  if (parts2.length === 1) {
    const one = oneTime(parts2[0]);
    return one && `${one} ${t("help.fps")}`;
  }
  if (parts2.length !== 2) return null;
  const [a, b] = parts2.map((p) => oneTime(p));
  if (!a || !b) return null;
  return `${t("help.time_range", { from: a, to: b })} ${t("help.fps")}`;
}
