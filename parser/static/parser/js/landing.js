(function(){
  const form = document.getElementById('uploadForm');
  const fileInput = document.getElementById('id_file');
  const dropzone = document.getElementById('dropzone');
  const chooseBtn = document.getElementById('chooseBtn');
  const fileNameEl = document.getElementById('fileName');
  const overlay = document.getElementById('loadingOverlay');
  const stageTitle = document.getElementById('stageTitle');
  const stageDesc = document.getElementById('stageDesc');
  const tiles = document.querySelectorAll('.tile');
  const cfgEl = document.getElementById('appConfig');

  // Config helpers
  function cfg(name){ return cfgEl ? cfgEl.getAttribute(name) : null; }
  const URLS = {
    upload: cfg('data-upload-url') || '/api/upload/',
    process: cfg('data-process-url') || '/api/process/',
    statusTmpl: cfg('data-status-url-tmpl') || '/api/status/{id}/',
    retry: cfg('data-retry-url') || '/api/retry/',
    downloadTmpl: cfg('data-download-url-tmpl') || '/download/{id}/{type}/'
  };

  // CSRF helper (Django)
  function getCookie(name){
    const cookies = document.cookie ? document.cookie.split('; ') : [];
    for(const c of cookies){
      const [k, v] = c.split('=');
      if(k === name) return decodeURIComponent(v);
    }
    return null;
  }
  const CSRF = getCookie('csrftoken');

  function showOverlay(title, desc){
    if(!overlay) return;
    overlay.classList.add('show');
    if(stageTitle) stageTitle.innerHTML = '<strong>' + (title || 'Working…') + '</strong>';
    if(stageDesc) stageDesc.textContent = desc || '';
    // Show OCR engine section when file is selected
    const ocrSection = document.getElementById('ocr-engine-section');
    if(ocrSection && fileInput && fileInput.files && fileInput.files.length) {
      ocrSection.style.display = 'block';
    }
  }
  function hideOverlay(){ overlay && overlay.classList.remove('show'); }
  window.addEventListener('beforeunload', hideOverlay);

  function updateFileName(){
    if(!fileNameEl) return;
    if(fileInput && fileInput.files && fileInput.files.length){
      fileNameEl.textContent = fileInput.files[0].name;
    } else {
      fileNameEl.textContent = '';
    }
  }

  // Choose button click triggers hidden input
  if(chooseBtn){
    chooseBtn.addEventListener('click', function(e){
      e.preventDefault();
      fileInput && fileInput.click();
    });
  }

  // Change event on input updates UI
  fileInput && fileInput.addEventListener('change', updateFileName);

  // Drag and drop handlers
  if(dropzone){
    // Click to open file chooser
    dropzone.addEventListener('click', function(e){
      // Avoid double-trigger when clicking the button inside
      if(e.target && (e.target.id === 'chooseBtn')) return;
      fileInput && fileInput.click();
    });
    // Keyboard access
    dropzone.addEventListener('keydown', function(e){
      if(e.key === 'Enter' || e.key === ' '){
        e.preventDefault();
        fileInput && fileInput.click();
      }
    });
    ;['dragenter','dragover'].forEach(evt => dropzone.addEventListener(evt, function(e){
      e.preventDefault(); e.stopPropagation(); this.classList.add('dragover');
    }));
    ;['dragleave','drop'].forEach(evt => dropzone.addEventListener(evt, function(e){
      e.preventDefault(); e.stopPropagation(); this.classList.remove('dragover');
    }));
    dropzone.addEventListener('drop', function(e){
      const dt = e.dataTransfer;
      if(!dt || !dt.files || dt.files.length===0) return;
      // accept only first file
      fileInput.files = dt.files;
      updateFileName();
    });
  }

  // Map tile selection to Django radios
  function setOutputFormat(val){
    const radio = document.querySelector('input[name="output_format"][value="' + val + '"]');
    if(radio){ radio.checked = true; }
    tiles.forEach(t => {
      const selected = t.getAttribute('data-value')===val;
      t.classList.toggle('selected', selected);
      t.setAttribute('aria-selected', selected ? 'true' : 'false');
    });
  }

  tiles.forEach(tile => {
    tile.addEventListener('click', function(){
      setOutputFormat(this.getAttribute('data-value'));
    });
  });

  // Initialize tile based on current radio
  const checked = document.querySelector('input[name="output_format"]:checked');
  if(checked){ setOutputFormat(checked.value); }

  // OCR Engine Selection Handling
  const ocrOptions = document.querySelectorAll('.ocr-option');
  
  function setOcrEngine(val){
    const radio = document.querySelector('input[name="ocr_engine"][value="' + val + '"]');
    if(radio){ radio.checked = true; }
    ocrOptions.forEach(option => {
      const selected = option.querySelector('input[type="radio"]').value === val;
      option.classList.toggle('selected', selected);
    });
  }

  ocrOptions.forEach(option => {
    option.addEventListener('click', function(){
      const radioInput = this.querySelector('input[type="radio"]');
      if(radioInput){
        setOcrEngine(radioInput.value);
      }
    });
  });

  // Initialize OCR engine based on current radio
  const checkedOcr = document.querySelector('input[name="ocr_engine"]:checked');
  if(checkedOcr){ setOcrEngine(checkedOcr.value); }

  // Stage mapping from backend to friendly messages
  const stageMessages = {
    uploading: { t: 'Uploading…', d: 'Sending your file securely.' },
    retrieving_file: { t: 'Retrieving file…', d: 'Preparing your document for processing.' },
    ocr: { t: 'OCR in progress…', d: 'Extracting text from your document.' },
    llm_parsing: { t: 'Understanding content…', d: 'Parsing and interpreting data.' },
    structuring: { t: 'Structuring data…', d: 'Normalizing and cleaning.' },
    file_generation: { t: 'Exporting…', d: 'Generating downloadable files.' },
    uploading_outputs: { t: 'Finalizing…', d: 'Uploading results securely.' },
    completed: { t: 'Done!', d: 'Preparing your download…' },
    failed: { t: 'Processing failed', d: 'Please try again.' }
  };

  function applyStage(stage, progress){
    const s = stageMessages[stage] || { t: 'Processing…', d: '' };
    const pct = (typeof progress === 'number') ? ` (${progress}%)` : '';
    showOverlay(`${s.t}${pct}`, s.d);
  }

  function getSelectedFormat(){
    const r = document.querySelector('input[name="output_format"]:checked');
    return r ? r.value : 'excel';
  }

  async function uploadFile(){
    const fd = new FormData(form);
    // Only include the first file input
    if(!(fileInput && fileInput.files && fileInput.files.length)){
      throw new Error('No file selected');
    }
    applyStage('uploading', 5);
    const resp = await fetch(URLS.upload, {
      method: 'POST',
      body: fd,
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        ...(CSRF ? { 'X-CSRFToken': CSRF } : {})
      }
    });
    const data = await resp.json().catch(()=>({ success:false, error:'Bad JSON' }));
    if(!resp.ok || !data.success){
      const msg = (data && data.error) ? data.error : `Upload failed (${resp.status})`;
      throw new Error(msg);
    }
    return data.document_id;
  }

  function startProcessing(documentId){
    // Fire and forget; backend does the heavy lifting
    try {
      fetch(URLS.process, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(CSRF ? { 'X-CSRFToken': CSRF } : {})
        },
        body: JSON.stringify({ document_id: documentId })
      }).catch(()=>{});
    } catch(_){ }
  }

  async function pollStatus(documentId){
    const url = URLS.statusTmpl.replace('{id}', String(documentId));
    try {
      const resp = await fetch(url, { method: 'GET' });
      const data = await resp.json();
      if(!data || data.success === false){
        throw new Error((data && data.error) || 'Status error');
      }
      const stage = data.stage || data.status || 'processing';
      const progress = data.progress;
      applyStage(stage, progress);
      if(data.status === 'completed'){
        // Auto download
        const fmt = getSelectedFormat();
        const dUrl = URLS.downloadTmpl
          .replace('{id}', String(documentId))
          .replace('{type}', fmt);
        // Give a brief moment for UX before download
        setTimeout(()=>{ window.location.href = dUrl; hideOverlay(); }, 400);
        return true;
      }
      if(data.status === 'failed'){
        const msg = data.error_message || 'Processing failed';
        showOverlay(stageMessages.failed.t, msg);
        setTimeout(hideOverlay, 1200);
        return true;
      }
      return false;
    } catch(err){
      // Transient network/JSON issues: keep overlay and retry
      showOverlay('Working…', 'Reconnecting to status…');
      return false;
    }
  }

  async function handleSubmit(e){
    e.preventDefault();
    if(!(fileInput && fileInput.files && fileInput.files.length)){
      fileInput && fileInput.focus();
      return;
    }
    try {
      // 1) Upload
      const documentId = await uploadFile();
      // 2) Start processing (non-blocking)
      startProcessing(documentId);
      // 3) Poll status
      let done = false;
      // First immediate poll to get early stage
      done = await pollStatus(documentId);
      if(done) return;
      const iv = setInterval(async () => {
        const finished = await pollStatus(documentId);
        if(finished){ clearInterval(iv); }
      }, 1500);
    } catch(err){
      showOverlay('Upload failed', (err && err.message) ? err.message : 'Please try again.');
      setTimeout(hideOverlay, 1500);
    }
  }

  // Submit handler
  if(form){
    form.addEventListener('submit', handleSubmit);
  }
})();
