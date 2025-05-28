import React, { useState, useCallback } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { setField, addChatMessage, clearForm, selectInteraction } from './interactionSlice';
import { nanoid } from '@reduxjs/toolkit';

// Apply Inter font globally in your main CSS or App.js/index.js
// For this component, we'll assume Inter is the default body font.
// e.g., in your index.css:
// body { font-family: 'Inter', sans-serif; }

const LogInteractionScreen = () => {
  const dispatch = useDispatch();
  const { form, chat } = useSelector(selectInteraction);
  const [mode, setMode] = useState('structured'); // 'structured' or 'chat'
  const [chatInput, setChatInput] = useState('');

  const handleFormChange = (e) => {
    dispatch(setField({ field: e.target.name, value: e.target.value }));
  };

  const handleFormSubmit = (e) => {
    e.preventDefault();
    // In a real app, you'd likely dispatch an async thunk here to save the form
    console.log('Structured Form Submitted:', form);
    // Example: dispatch(saveInteraction(form));
    // dispatch(clearForm());
    alert('Interaction logged (structured). Check console.');
  };

  const handleChatInputChange = (e) => {
    setChatInput(e.target.value);
  };

  const handleChatSubmit = async (e) => {
  e.preventDefault();
  if (!chatInput.trim()) return;


    const userMessage = { id: nanoid(), sender: 'user', text: chatInput, timestamp: new Date().toISOString() };
  dispatch(addChatMessage(userMessage));

    try {
    const response = await fetch('http://localhost:8000/api/chat_interaction', {  // FULL URL here
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: chatInput, history: chat.messages }),
    });

      if (!response.ok) {
        throw new Error(`API error: ${response.statusText}`);
      }

      const aiResponseData = await response.json();
      // The AI response might contain structured data or just a conversational reply
      // For simplicity, we'll assume it's a conversational reply here.
      // The LangGraph agent should ideally parse the conversation and populate
      // the interaction log fields, which could then update the Redux store.

      const aiMessage = {
        id: nanoid(),
        sender: 'ai',
        text: aiResponseData.reply || "I've processed your request.", // Adjust based on actual AI response
        timestamp: new Date().toISOString(),
        extractedData: aiResponseData.extracted_data || null // If AI extracts data
      };
      dispatch(addChatMessage(aiMessage));

      // If AI extracted data, you might want to pre-fill or update the structured form
      if (aiMessage.extractedData) {
        Object.entries(aiMessage.extractedData).forEach(([key, value]) => {
          dispatch(setField({ field: key, value }));
        });
        // Potentially switch to structured mode or show a confirmation
         alert('AI has extracted data. Review the form or continue chatting.');
      }

    } catch (error) {
      console.error('Error sending chat message:', error);
      const errorMessage = { id: nanoid(), sender: 'ai', text: `Error: ${error.message}`, timestamp: new Date().toISOString() };
      dispatch(addChatMessage(errorMessage));
    } finally {
      setChatInput('');
    }
  };


  const commonInputStyles = "mt-1 block w-full px-3 py-2 bg-white border border-slate-300 rounded-md text-sm shadow-sm placeholder-slate-400 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500 disabled:bg-slate-50 disabled:text-slate-500 disabled:border-slate-200 disabled:shadow-none invalid:border-pink-500 invalid:text-pink-600 focus:invalid:border-pink-500 focus:invalid:ring-pink-500";
  const commonLabelStyles = "block text-sm font-medium text-slate-700";
  const commonButtonStyles = "px-4 py-2 font-semibold text-sm bg-sky-500 text-white rounded-md shadow-sm hover:bg-sky-600 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:ring-offset-2";

  return (
    <div style={{ fontFamily: "'Inter', sans-serif" }} className="p-6 max-w-2xl mx-auto bg-slate-50 rounded-xl shadow-lg">
      <h1 className="text-2xl font-bold text-slate-800 mb-6 text-center">Log HCP Interaction</h1>

      <div className="mb-4 flex justify-center">
        <button
          onClick={() => setMode('structured')}
          className={`mr-2 ${commonButtonStyles} ${mode === 'structured' ? 'bg-sky-700' : 'bg-slate-400 hover:bg-slate-500'}`}
        >
          Structured Form
        </button>
        <button
          onClick={() => setMode('chat')}
          className={`${commonButtonStyles} ${mode === 'chat' ? 'bg-sky-700' : 'bg-slate-400 hover:bg-slate-500'}`}
        >
          Conversational Chat
        </button>
      </div>

      {mode === 'structured' && (
        <form onSubmit={handleFormSubmit} className="space-y-4">
          <div>
            <label htmlFor="hcpName" className={commonLabelStyles}>HCP Name:</label>
            <input type="text" name="hcpName" id="hcpName" value={form.hcpName || ''} onChange={handleFormChange} className={commonInputStyles} required />
          </div>
          <div>
            <label htmlFor="interactionDate" className={commonLabelStyles}>Date of Interaction:</label>
            <input type="date" name="interactionDate" id="interactionDate" value={form.interactionDate || ''} onChange={handleFormChange} className={commonInputStyles} required />
          </div>
          <div>
            <label htmlFor="interactionType" className={commonLabelStyles}>Type of Interaction:</label>
            <select name="interactionType" id="interactionType" value={form.interactionType || 'detail'} onChange={handleFormChange} className={commonInputStyles}>
              <option value="detail">Detail</option>
              <option value="follow-up">Follow-up</option>
              <option value="sample_drop">Sample Drop</option>
              <option value="meeting">Meeting</option>
              <option value="other">Other</option>
            </select>
          </div>
          <div>
            <label htmlFor="productsDiscussed" className={commonLabelStyles}>Products Discussed (comma-separated):</label>
            <input type="text" name="productsDiscussed" id="productsDiscussed" value={form.productsDiscussed || ''} onChange={handleFormChange} className={commonInputStyles} />
          </div>
          <div>
            <label htmlFor="keyDiscussionPoints" className={commonLabelStyles}>Key Discussion Points:</label>
            <textarea name="keyDiscussionPoints" id="keyDiscussionPoints" value={form.keyDiscussionPoints || ''} onChange={handleFormChange} rows="4" className={commonInputStyles}></textarea>
          </div>
          <div>
            <label htmlFor="followUpActions" className={commonLabelStyles}>Follow-up Actions:</label>
            <textarea name="followUpActions" id="followUpActions" value={form.followUpActions || ''} onChange={handleFormChange} rows="3" className={commonInputStyles}></textarea>
          </div>
          <div className="flex justify-end space-x-3">
            <button type="button" onClick={() => dispatch(clearForm())} className={`${commonButtonStyles} bg-slate-300 hover:bg-slate-400 text-slate-800`}>
              Clear
            </button>
            <button type="submit" className={commonButtonStyles}>
              Log Interaction
            </button>
          </div>
        </form>
      )}

      {mode === 'chat' && (
        <div className="flex flex-col h-[500px] bg-white shadow-inner rounded-lg p-4">
          <div className="flex-grow overflow-y-auto mb-4 space-y-2 pr-2">
            {chat.messages.map((msg) => (
              <div key={msg.id} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg shadow ${msg.sender === 'user' ? 'bg-sky-500 text-white' : 'bg-slate-200 text-slate-800'}`}>
                  <p className="text-sm">{msg.text}</p>
                  <p className="text-xs text-opacity-75 mt-1">
                    {new Date(msg.timestamp).toLocaleTimeString()}
                    {msg.sender === 'ai' && msg.extractedData && <span className="italic block text-xs"> (Data extracted)</span>}
                  </p>
                </div>
              </div>
            ))}
          </div>
          <form onSubmit={handleChatSubmit} className="flex">
            <input
              type="text"
              value={chatInput}
              onChange={handleChatInputChange}
              placeholder="Describe the interaction..."
              className={`${commonInputStyles} flex-grow mr-2`}
            />
            <button type="submit" className={commonButtonStyles}>Send</button>
          </form>
        </div>
      )}
    </div>
  );
};

export default LogInteractionScreen;