import { QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";

export const getRouter = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        // A control-room screen must fail visibly and quickly. React Query's
        // default of three retries with exponential backoff leaves a screen
        // sitting on "LOADING" for the better part of a minute when the backend
        // is down, which reads as a hang rather than as an outage. One quick
        // retry covers a transient blip; anything worse surfaces the error
        // state, which names the command that fixes it.
        retry: 1,
        retryDelay: 800,
        refetchOnWindowFocus: false,
      },
    },
  });

  const router = createRouter({
    routeTree,
    context: { queryClient },
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
  });

  return router;
};
