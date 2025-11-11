"""
Memory Management Service for LangGraph Agents

This service implements a hybrid memory management strategy to prevent context window overflow
and optimize token usage in conversational agents.

The hybrid strategy automatically:
1. Removes tool messages (reduce noise)
2. Trims to maximum number of messages
3. Enforces token limits if specified
4. (Future) Summarizes old messages when threshold is reached
"""

from typing import List, Dict, Any, Optional
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage
import tiktoken
from utils.logger import get_logger

logger = get_logger(__name__)


class MemoryManagementService:
    """Service for managing agent conversation memory"""
    
    # Default encoding for token counting (works for most OpenAI models)
    DEFAULT_ENCODING = "cl100k_base"
    
    @staticmethod
    def count_tokens(messages: List[BaseMessage], encoding_name: str = DEFAULT_ENCODING) -> int:
        """
        Count the number of tokens in a list of messages.
        
        Args:
            messages: List of LangChain messages
            encoding_name: Tiktoken encoding to use
            
        Returns:
            Total number of tokens
        """
        try:
            encoding = tiktoken.get_encoding(encoding_name)
            total_tokens = 0
            
            for message in messages:
                # Count tokens in message content
                if hasattr(message, 'content') and message.content:
                    total_tokens += len(encoding.encode(str(message.content)))
                
                # Add overhead for message formatting (~4 tokens per message)
                total_tokens += 4
                
            return total_tokens
        except Exception as e:
            logger.warning(f"Error counting tokens: {e}. Falling back to character estimation.")
            # Fallback: estimate ~4 characters per token
            total_chars = sum(len(str(m.content)) for m in messages if hasattr(m, 'content'))
            return total_chars // 4
    
    @staticmethod
    def trim_messages(
        messages: List[BaseMessage], 
        max_messages: int,
        keep_system: bool = True
    ) -> List[BaseMessage]:
        """
        Trim messages to keep only the most recent ones.
        
        Args:
            messages: List of messages to trim
            max_messages: Maximum number of messages to keep
            keep_system: Whether to always keep system messages
            
        Returns:
            Trimmed list of messages
        """
        if len(messages) <= max_messages:
            return messages
        
        # Separate system messages from conversation messages
        system_messages = [m for m in messages if isinstance(m, SystemMessage)]
        conversation_messages = [m for m in messages if not isinstance(m, SystemMessage)]
        
        # Keep the most recent N conversation messages
        if len(conversation_messages) > max_messages:
            conversation_messages = conversation_messages[-max_messages:]
        
        # Recombine: system messages first, then trimmed conversation
        if keep_system:
            result = system_messages + conversation_messages
        else:
            result = conversation_messages
        
        logger.info(f"Trimmed messages from {len(messages)} to {len(result)}")
        return result
    
    @staticmethod
    def remove_tool_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Remove tool call and tool response messages to reduce noise.
        IMPORTANT: Always keeps tool_calls and their responses together to maintain
        OpenAI API requirements (each tool_call must have a corresponding response).
        
        Args:
            messages: List of messages
            
        Returns:
            Filtered list without tool messages (or all messages if last is a tool_call)
        """
        # Check if the last AI message has pending tool_calls
        # If so, don't remove any tool messages to avoid breaking OpenAI's requirements
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if isinstance(msg, AIMessage):
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    # Found an AI message with tool_calls
                    # Check if there's ANOTHER AIMessage after the tool responses
                    # If not, these tool responses haven't been processed yet
                    has_next_ai_message = False
                    for j in range(i + 1, len(messages)):
                        if isinstance(messages[j], AIMessage):
                            has_next_ai_message = True
                            break
                    
                    # If there's no AI message after the tool_calls,
                    # it means the tool responses haven't been processed yet
                    if not has_next_ai_message:
                        logger.info("Keeping all tool messages - tool responses not yet processed by LLM")
                        return messages
                break
        
        # Safe to remove tool messages - no pending tool_calls
        filtered = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            
            # Check if this is an AIMessage with tool_calls
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                # Get tool_call_ids from this message
                tool_call_ids = {tc.get('id') if isinstance(tc, dict) else tc.id for tc in msg.tool_calls}
                
                # Find all corresponding ToolMessages
                j = i + 1
                tool_messages_to_skip = []
                while j < len(messages):
                    if isinstance(messages[j], ToolMessage):
                        if hasattr(messages[j], 'tool_call_id') and messages[j].tool_call_id in tool_call_ids:
                            tool_messages_to_skip.append(j)
                            tool_call_ids.discard(messages[j].tool_call_id)
                    elif not isinstance(messages[j], ToolMessage):
                        # Stop when we hit a non-ToolMessage
                        break
                    j += 1
                
                # Only remove the AIMessage if it has no content (only tool calls)
                if not msg.content and tool_messages_to_skip:
                    # Skip this AIMessage and its ToolMessages
                    i = max(tool_messages_to_skip) + 1
                    continue
                else:
                    # Keep the AIMessage, skip only the ToolMessages
                    filtered.append(msg)
                    i = max(tool_messages_to_skip) + 1 if tool_messages_to_skip else i + 1
                    continue
            
            # Keep non-tool messages
            if not isinstance(msg, ToolMessage):
                filtered.append(msg)
            
            i += 1
        
        if len(filtered) < len(messages):
            logger.info(f"Removed {len(messages) - len(filtered)} tool messages")
        
        return filtered
    
    @staticmethod
    async def summarize_messages(
        messages: List[BaseMessage],
        llm: Any,
        max_summary_length: int = 500
    ) -> BaseMessage:
        """
        Summarize a list of messages into a single summary message.
        
        Args:
            messages: List of messages to summarize
            llm: Language model to use for summarization
            max_summary_length: Maximum length of summary in characters
            
        Returns:
            SystemMessage containing the summary
        """
        try:
            # Build conversation text
            conversation_text = ""
            for msg in messages:
                if isinstance(msg, HumanMessage):
                    conversation_text += f"Usuario: {msg.content}\n"
                elif isinstance(msg, AIMessage):
                    conversation_text += f"Asistente: {msg.content}\n"
            
            # Create summarization prompt
            summary_prompt = f"""Resume la siguiente conversación de forma concisa, manteniendo los puntos clave y el contexto importante.
Máximo {max_summary_length} caracteres.

Conversación:
{conversation_text}

Resumen:"""
            
            # Get summary from LLM
            response = await llm.ainvoke(summary_prompt)
            summary = response.content if hasattr(response, 'content') else str(response)
            
            logger.info(f"Summarized {len(messages)} messages into {len(summary)} characters")
            
            return SystemMessage(content=f"[Resumen de conversación anterior]: {summary}")
        
        except Exception as e:
            logger.error(f"Error summarizing messages: {e}")
            # Fallback: create a simple summary
            return SystemMessage(content=f"[Resumen]: Conversación con {len(messages)} mensajes previos.")
    
    @staticmethod
    def apply_hybrid_strategy(
        messages: List[BaseMessage],
        max_messages: int = 50,
        max_tokens: Optional[int] = None
    ) -> List[BaseMessage]:
        """
        Apply simplified memory management strategy to messages.
        
        This simplified version only:
        1. Counts tokens and logs statistics
        2. Preserves ALL messages to avoid breaking tool_calls/responses
        
        Args:
            messages: List of messages to process
            max_messages: Maximum number of messages to keep (currently ignored)
            max_tokens: Maximum number of tokens to keep (currently ignored)
            
        Returns:
            Original list of messages (no filtering applied)
        """
        if not messages:
            return messages
        
        original_count = len(messages)
        original_tokens = MemoryManagementService.count_tokens(messages)
        
        # For now, just return all messages without any filtering
        # This prevents breaking tool_calls and their responses
        processed = messages
        
        # Log statistics
        processed_tokens = MemoryManagementService.count_tokens(processed)
        logger.info(f"Memory management: {original_count} msgs ({original_tokens} tokens) -> "
                   f"{len(processed)} msgs ({processed_tokens} tokens)")
        
        return processed
    
    @staticmethod
    def get_memory_stats(messages: List[BaseMessage]) -> Dict[str, Any]:
        """
        Get statistics about message memory usage.
        
        Args:
            messages: List of messages to analyze
            
        Returns:
            Dictionary with statistics
        """
        stats = {
            'total_messages': len(messages),
            'total_tokens': MemoryManagementService.count_tokens(messages),
            'message_types': {}
        }
        
        for msg in messages:
            msg_type = type(msg).__name__
            stats['message_types'][msg_type] = stats['message_types'].get(msg_type, 0) + 1
        
        return stats

