import { configureStore } from '@reduxjs/toolkit';
import interactionReducer from './interactionSlice'; // Adjust path if needed

export const store = configureStore({
  reducer: {
    interaction: interactionReducer,
  },
});
