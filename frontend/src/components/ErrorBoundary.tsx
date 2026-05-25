import { Component, type ReactNode } from "react";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

interface State {
  error: Error | null;
}

interface Props {
  children: ReactNode;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error) {
    toast.error(`Application error: ${error.message}`);
    console.error("Render error:", error);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="flex h-screen items-center justify-center p-8">
        <div className="max-w-md rounded-lg border bg-card p-6 text-center shadow-md">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-destructive/10 text-destructive">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <h1 className="text-lg font-semibold">Something went wrong</h1>
          <p className="mt-2 break-words text-sm text-muted-foreground">
            {this.state.error.message}
          </p>
          <Button onClick={this.reset} className="mt-4">
            Try again
          </Button>
        </div>
      </div>
    );
  }
}
