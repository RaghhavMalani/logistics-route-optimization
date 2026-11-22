import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const estimateExplanation =
  "Estimated from when the forecast values last changed; the provider does not publish the model run time.";

export function ForecastReceiptText({ text }: { text: string }) {
  const marker = text.indexOf("~");
  if (marker < 0) return text;
  return (
    <>
      {text.slice(0, marker)}
      <TooltipProvider delayDuration={250}>
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              tabIndex={0}
              className="cursor-help"
              aria-label="Estimated forecast issue time"
              data-testid="forecast-issue-estimate"
            >
              ~
            </span>
          </TooltipTrigger>
          <TooltipContent className="max-w-xs">
            {estimateExplanation}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      {text.slice(marker + 1)}
    </>
  );
}
