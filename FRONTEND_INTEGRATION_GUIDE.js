/**
 * FRONTEND INTEGRATION GUIDE
 * Document Link Feature - Backend Ready
 * 
 * The backend now provides clickable citation links that open documents
 * to the specific page where the answer came from.
 */

// ============================================================================
// 1. SSE RESPONSE STRUCTURE
// ============================================================================
// When the chatbot responds, the SSE stream includes a 'done' event with:
// 
// Example SSE response structure:
// {
//   "type": "done",
//   "citation": "Source: Leaves & Holidays - Leave Types & Entitlements, STEMZ Healthcare HR Playbook [HR-Playbook.md]",
//   "confidence": 0.95,
//   "source": {
//     "citation_link": "/view-document/?file=HR-Playbook.md&page=5",
//     "page_number": 5,
//     "source_file": "HR-Playbook.md",
//     "source_type": "md",
//     "section": "Leaves & Holidays - Leave Types & Entitlements",
//     "doc_title": "STEMZ Healthcare HR Playbook",
//     "category": "HR Policies",
//     "version": "1",
//     "effective_date": "2026-09-09",
//     "status": "active",
//     "excerpt": "Casual Leave (CL): 7 days/year, accrues 0.58 days/month..."
//   }
// }

// ============================================================================
// 2. MAKING CITATIONS CLICKABLE
// ============================================================================
// Option A: Simple Approach - Make citation text clickable

function renderCitation(source) {
  if (!source.citation_link) {
    return source.section || "Document";
  }
  
  return `<a href="${source.citation_link}" target="_blank" class="citation-link">
    📄 View in Document (Page ${source.page_number})
  </a>`;
}

// Option B: Enhanced - Show both text and link

function renderEnhancedCitation(source) {
  const citationText = `Source: ${source.section || ''}, ${source.doc_title}`;
  const viewLink = source.citation_link ? 
    `<a href="${source.citation_link}" target="_blank" class="view-doc-link">View</a>` : 
    '';
  
  return `
    <div class="citation">
      <span class="citation-text">${citationText}</span>
      ${viewLink}
      <span class="page-badge">Page ${source.page_number}</span>
    </div>
  `;
}

// ============================================================================
// 3. CLICK HANDLING
// ============================================================================
// When user clicks the citation link:

document.addEventListener('click', function(e) {
  if (e.target.classList.contains('citation-link')) {
    const link = e.target.href;
    
    // Option 1: Open in new tab (recommended)
    window.open(link, '_blank');
    
    // Option 2: Open in modal/iframe
    showDocumentModal(link);
    
    // Option 3: Track analytics
    trackEvent('citation_click', {
      document: e.target.dataset.document,
      page: e.target.dataset.page
    });
  }
});

// ============================================================================
// 4. DOCUMENT VIEWER MODAL (OPTIONAL)
// ============================================================================
// If you want to show the document within the chat interface:

function showDocumentModal(viewerUrl) {
  const modal = document.createElement('div');
  modal.className = 'document-modal';
  modal.innerHTML = `
    <div class="modal-content">
      <div class="modal-header">
        <h2>Document Viewer</h2>
        <button class="close-btn">&times;</button>
      </div>
      <div class="modal-body">
        <iframe src="${viewerUrl}" class="document-frame"></iframe>
      </div>
    </div>
  `;
  
  document.body.appendChild(modal);
  
  modal.querySelector('.close-btn').addEventListener('click', () => {
    modal.remove();
  });
}

// ============================================================================
// 5. CSS STYLING
// ============================================================================
/*
.citation {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 12px;
  background: #f0f7ff;
  border-left: 3px solid #007bff;
  border-radius: 4px;
  font-size: 14px;
}

.citation-link {
  color: #007bff;
  text-decoration: none;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.2s;
}

.citation-link:hover {
  color: #0056b3;
  text-decoration: underline;
}

.page-badge {
  background: #007bff;
  color: white;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: bold;
  white-space: nowrap;
}

.document-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  width: 90%;
  height: 90%;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
}

.document-frame {
  flex: 1;
  border: none;
  border-radius: 4px;
}
*/

// ============================================================================
// 6. EXAMPLE INTEGRATION IN REACT
// ============================================================================
/*
import React, { useEffect, useState } from 'react';

function CitationComponent({ source }) {
  const [showModal, setShowModal] = useState(false);
  
  if (!source || !source.citation_link) {
    return <span>{source?.section || 'Document'}</span>;
  }
  
  return (
    <>
      <div className="citation">
        <span className="citation-text">
          Source: {source.section}, {source.doc_title}
        </span>
        <a 
          href="#"
          className="citation-link"
          onClick={(e) => {
            e.preventDefault();
            setShowModal(true);
          }}
        >
          📄 View Document
        </a>
        <span className="page-badge">Page {source.page_number}</span>
      </div>
      
      {showModal && (
        <DocumentModal 
          url={source.citation_link}
          onClose={() => setShowModal(false)}
        />
      )}
    </>
  );
}

function DocumentModal({ url, onClose }) {
  return (
    <div className="document-modal" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Document Viewer</h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>
        <iframe src={url} className="document-frame" title="Document" />
      </div>
    </div>
  );
}

export default CitationComponent;
*/

// ============================================================================
// 7. BACKEND ENDPOINTS REFERENCE
// ============================================================================
/*
GET /view-document/?file=filename.docx&page=5

Parameters:
  - file (string): Document filename from knowledge/new-knowledge/
  - page (integer): Page number (optional, default 1)

Response:
  - HTML page with download button and instructions
  - File must be in knowledge/new-knowledge/ directory
  - Path traversal attempts are blocked

Example URLs:
  /view-document/?file=HR-Playbook.md&page=5
  /view-document/?file=HR%20Playbook%20-%2009092026.docx&page=3
*/

// ============================================================================
// 8. TESTING THE FEATURE
// ============================================================================
/*
1. Start the server:
   python manage.py runserver

2. Ask a question in the chat:
   "What is the maternity leave policy?"

3. Check the browser console (F12 → Console) to see the SSE response:
   The 'done' event should include:
   - source.citation_link: "/view-document/?file=HR-Playbook.md&page=5"
   - source.page_number: 5

4. Implement the frontend rendering using the examples above

5. Test clicking the citation link - should open document viewer
*/
