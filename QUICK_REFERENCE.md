# 🔗 DOCUMENT LINK FEATURE - QUICK REFERENCE

## What Appears in SSE Response:

Every time the chatbot responds with a citation, you'll receive this in the SSE stream:

```json
{
  "type": "done",
  "citation": "Source: Attendance Rules - Work From Home Entitlement, STEMZ Healthcare HR Playbook [HR-Playbook.md]",
  "confidence": 0.95,
  "source": {
    "citation_link": "/view-document/?file=HR-Playbook.md&page=1",
    "page_number": 1,
    "source_file": "HR-Playbook.md",
    "source_type": "md"
  }
}
```

## Frontend Code to Use:

### 1️⃣ Listen for SSE Response:

```javascript
const eventSource = new EventSource('/api/chat/');

eventSource.addEventListener('done', (event) => {
  const data = JSON.parse(event.data);
  
  // Extract what we need
  const citationLink = data.source?.citation_link;
  const pageNumber = data.source?.page_number;
  const sourceFile = data.source?.source_file;
  
  // Render citation with link
  renderCitation(citationLink, pageNumber, sourceFile);
});
```

### 2️⃣ Render Citation as Clickable Link:

```javascript
function renderCitation(citationLink, pageNumber, sourceFile) {
  if (!citationLink) return; // No link available
  
  const citationHTML = `
    <a href="${citationLink}" target="_blank" class="citation-link">
      📄 View Source (Page ${pageNumber}) - ${sourceFile}
    </a>
  `;
  
  document.getElementById('citation-container').innerHTML = citationHTML;
}
```

### 3️⃣ Add CSS:

```css
.citation-link {
  display: inline-block;
  background: #f0f7ff;
  border-left: 3px solid #007bff;
  padding: 10px 12px;
  margin-top: 10px;
  color: #007bff;
  text-decoration: none;
  border-radius: 4px;
  font-size: 14px;
  transition: all 0.2s ease;
}

.citation-link:hover {
  background: #e7f3ff;
  border-left-color: #0056b3;
  color: #0056b3;
  transform: translateX(4px);
}
```

---

## Exact Implementation (Copy-Paste Ready):

### HTML:
```html
<div id="chat-message">
  <p id="message-content"></p>
  <div id="citation-container"></div>
</div>
```

### JavaScript:
```javascript
// Parse SSE response
eventSource.addEventListener('done', (event) => {
  const response = JSON.parse(event.data);
  
  // Show message content
  document.getElementById('message-content').textContent = response.content;
  
  // Show citation with link
  if (response.source?.citation_link) {
    document.getElementById('citation-container').innerHTML = `
      <a href="${response.source.citation_link}" 
         target="_blank" 
         class="citation-link">
        📄 View in Document - Page ${response.source.page_number}
      </a>
    `;
  }
});
```

---

## Testing Checklist:

- [ ] Server running: `python manage.py runserver`
- [ ] Chat page loads: `http://localhost:8000`
- [ ] Browser console open: F12 → Console
- [ ] Ask question: "What is the WFH policy?"
- [ ] Check SSE response for `citation_link` and `page_number`
- [ ] Implement HTML/JS from above
- [ ] Refresh page and try again
- [ ] Click citation link → Document viewer opens
- [ ] Page number matches expectation

---

## Debug: Checking SSE Response

1. Open DevTools (F12)
2. Go to Console tab
3. Run this code:

```javascript
const eventSource = new EventSource('/api/chat/');
eventSource.addEventListener('done', (event) => {
  console.log('SSE Response:', JSON.parse(event.data));
});
```

4. Ask a question in the chat
5. See the response in console - look for `source.citation_link`

---

## URL Format Reference:

```
/view-document/?file={filename}&page={pageNumber}

Examples:
/view-document/?file=HR-Playbook.md&page=1
/view-document/?file=HR%20Playbook%20-%2009092026.docx&page=5
```

---

## Files to Reference:

1. **FEATURE_SUMMARY.md** - Visual overview
2. **DOCUMENT_LINK_FEATURE.md** - Full detailed documentation
3. **FRONTEND_INTEGRATION_GUIDE.js** - Code examples in JavaScript/React
4. **This file** - Quick reference for copy-paste implementation

---

**That's it! 3 simple steps to add the feature.**

Good luck! 🚀
