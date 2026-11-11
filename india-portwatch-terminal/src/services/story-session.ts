const STORY_KEY = "portwatch.story.v1";

export interface StorySession {
  step: number;
  decisionId?: string;
  optionId?: string;
  advisoryId?: string;
}

export function readStory(): StorySession | null {
  try {
    const stored = window.sessionStorage.getItem(STORY_KEY);
    if (!stored) return null;
    const story = JSON.parse(stored) as StorySession;
    return Number.isInteger(story.step) && story.step >= 0 ? story : null;
  } catch {
    return null;
  }
}

export function writeStory(story: StorySession | null) {
  if (story) window.sessionStorage.setItem(STORY_KEY, JSON.stringify(story));
  else window.sessionStorage.removeItem(STORY_KEY);
  window.dispatchEvent(new Event("portwatch:story"));
}
