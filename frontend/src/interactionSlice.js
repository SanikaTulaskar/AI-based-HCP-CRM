import { createSlice, nanoid } from '@reduxjs/toolkit';

const initialState = {
  form: {
    hcpName: '',
    interactionDate: new Date().toISOString().split('T')[0], // Default to today
    interactionType: 'detail',
    productsDiscussed: '',
    keyDiscussionPoints: '',
    followUpActions: '',
  },
  chat: {
    messages: [
        { id: nanoid(), sender: 'ai', text: 'Hi! How can I help you log your HCP interaction today?', timestamp: new Date().toISOString() }
    ],
    isLoading: false,
  },
  // You might want to store a list of saved interactions here as well
  // savedInteractions: [],
};

const interactionSlice = createSlice({
  name: 'interaction',
  initialState,
  reducers: {
    setField: (state, action) => {
      const { field, value } = action.payload;
      state.form[field] = value;
    },
    clearForm: (state) => {
      state.form = initialState.form;
    },
    addChatMessage: (state, action) => {
      state.chat.messages.push(action.payload);
    },
    setChatLoading: (state, action) => {
      state.chat.isLoading = action.payload;
    },
    // Example: if AI directly provides full form data after chat
    setFormFromChat: (state, action) => {
        state.form = { ...state.form, ...action.payload };
    }
    // Add other reducers as needed, e.g., for saving interaction, loading interactions
  },
});

export const { setField, clearForm, addChatMessage, setChatLoading, setFormFromChat } = interactionSlice.actions;

export const selectInteraction = (state) => state.interaction;
export const selectForm = (state) => state.interaction.form;
export const selectChatMessages = (state) => state.interaction.chat.messages;

export default interactionSlice.reducer;

// Example of an async thunk (you'd typically put this in a separate file or here)
// import { createAsyncThunk } from '@reduxjs/toolkit';
//
// export const saveInteraction = createAsyncThunk(
//   'interactions/saveInteraction',
//   async (interactionData, { rejectWithValue }) => {
//     try {
//       const response = await fetch('/api/interactions', { // FastAPI endpoint
//         method: 'POST',
//         headers: { 'Content-Type': 'application/json' },
//         body: JSON.stringify(interactionData),
//       });
//       if (!response.ok) {
//         const error = await response.json();
//         return rejectWithValue(error);
//       }
//       return await response.json();
//     } catch (err) {
//       return rejectWithValue(err.message);
//     }
//   }
// );
//
// And then handle it in extraReducers:
// extraReducers: (builder) => {
//   builder
//     .addCase(saveInteraction.pending, (state) => {
//       state.status = 'loading';
//     })
//     .addCase(saveInteraction.fulfilled, (state, action) => {
//       state.status = 'succeeded';
//       // Add the new interaction to the list or update state as needed
//       // state.savedInteractions.push(action.payload);
//       // Or simply clear the form on success
//       state.form = initialState.form;
//     })
//     .addCase(saveInteraction.rejected, (state, action) => {
//       state.status = 'failed';
//       state.error = action.payload;
//     });
// }