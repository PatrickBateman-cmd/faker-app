export interface DomainInfo {
  id: string;
  name: string;
}

export interface MessageInfo {
  message_id: string;
  message_name: string;
  submitting_org: string;
  business_area: string;
  xsd_url: string | null;
}

export interface ParsedField {
  name: string;
  xsd_type: string;
  mapped_generator: string;
  min_occurs: number;
  max_occurs: string;
  documentation: string | null;
  enumeration_values: string[] | null;
  nested_fields: ParsedField[] | null;
}

export interface XsdParsedResponse {
  message_id: string;
  message_name: string;
  namespace: string | null;
  fields: ParsedField[];
}
